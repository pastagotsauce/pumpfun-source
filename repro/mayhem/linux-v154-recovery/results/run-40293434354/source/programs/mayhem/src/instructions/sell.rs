//! Legacy sell recovered from the original dispatch, parsers and arithmetic.
use anchor_lang::prelude::*;
use anchor_lang::solana_program::{instruction::Instruction,program::invoke_signed};
use anchor_spl::token_interface::{Mint,TokenAccount};
use anchor_spl::token_2022::Token2022;
use crate::{GlobalParams,MayhemError};
use crate::state::{MayhemState,MayhemStatus,PUMP_ID};
use crate::checked_program::{CheckedSystemProgram,CheckedSystemProgramBumps,__client_accounts_checked_system_program,__cpi_client_accounts_checked_system_program};

#[derive(Accounts)]
pub struct LegacySell<'info> {
 #[account(mut)]pub trader:Signer<'info>,
 #[account(mut,seeds=[b"global-params"],bump,has_one=trader)]pub global_params:Box<Account<'info,GlobalParams>>,
 #[account(mut,seeds=[b"mayhem-state",mint.key().as_ref()],bump)]pub mayhem_state:Box<Account<'info,MayhemState>>,
 /// CHECK: Original unchecked PDA and mutable constraints.
 #[account(mut,seeds=[b"sol-vault"],bump)]pub sol_vault:UncheckedAccount<'info>,
 pub mint:Box<InterfaceAccount<'info,Mint>>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=sol_vault,associated_token::token_program=mint.to_account_info().owner)]pub mayhem_token_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 pub token_program:Program<'info,Token2022>,
 pub system_program:CheckedSystemProgram<'info>,
 /// CHECK: Passed through to Pump; original unchecked account.
 pub global:UncheckedAccount<'info>,
 #[account(mut,seeds=[b"bonding-curve",mint.key().as_ref()],bump,seeds::program=PUMP_ID)]pub bonding_curve:Box<Account<'info,SellCurve>>,
 /// CHECK: Pump validates fee recipient.
 #[account(mut)]pub fee_recipient:UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=bonding_curve,associated_token::token_program=mint.to_account_info().owner)]pub associated_bonding_curve:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: Pump validates creator vault.
 #[account(mut)]pub creator_vault:UncheckedAccount<'info>,
 /// CHECK: Pump event authority passed through.
 pub pump_event_authority:UncheckedAccount<'info>,
 /// CHECK: Original address constraint, without executable Program wrapper.
 #[account(address=PUMP_ID)]pub pump_program:UncheckedAccount<'info>,
 /// CHECK: Pump validates its fee config.
 pub fee_config:UncheckedAccount<'info>,
 /// CHECK: Pump validates its fee program.
 pub fee_program:UncheckedAccount<'info>,
 /// CHECK: Original runtime event PDA constraint.
 #[account(seeds=[b"__event_authority"],bump)]pub event_authority:UncheckedAccount<'info>,
 pub program:Program<'info,crate::program::MayhemRecovered>,
 /// CHECK: Original derives this under Mayhem, not the Pump program.
 #[account(seeds=[b"bonding-curve-v2",mint.key().as_ref()],bump)]pub bonding_curve_v2:UncheckedAccount<'info>,
 /// CHECK: Pump validates the recipient when used.
 #[account(mut)]pub buyback_recipient:UncheckedAccount<'info>,
}
/// The sell path uses the padded external-account decoder at 0xac0, reached
/// from 0x5258 -> 0xa248 -> 0x66a0 and by reload at 0x5fb0. It pads short
/// input to 141 zero bytes before the ordinary decoder at 0x84108. This is
/// intentionally separate from the older, strict 82-byte burn account codec.
#[derive(Clone)]
pub struct SellCurve {
 pub virtual_token_reserves:u64,pub virtual_sol_reserves:u64,
 pub real_token_reserves:u64,pub real_sol_reserves:u64,
}
impl Owner for SellCurve {fn owner()->Pubkey {PUMP_ID}}
impl AccountSerialize for SellCurve {}
impl AccountDeserialize for SellCurve {
 fn try_deserialize(buf:&mut &[u8])->Result<Self>{Self::try_deserialize_unchecked(buf)}
 fn try_deserialize_unchecked(buf:&mut &[u8])->Result<Self>{
  let mut padded=[0u8;141];let n=buf.len().min(padded.len());padded[..n].copy_from_slice(&buf[..n]);
  if padded[..8]!=[0x17,0xb7,0xf8,0x37,0x60,0xd8,0xac,0x60] {return Err(anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch.into());}
  for offset in [48,81,82,123,124] {if padded[offset]>1 {return Err(anchor_lang::error::ErrorCode::AccountDidNotDeserialize.into());}}
  let read=|offset:usize|u64::from_le_bytes(padded[offset..offset+8].try_into().unwrap());
  Ok(Self{virtual_token_reserves:read(8),virtual_sol_reserves:read(16),real_token_reserves:read(24),real_sol_reserves:read(32)})
 }
}
fn math()->Error {MayhemError::MathOverflow.into()}
pub fn handler(ctx:Context<LegacySell>,reference:u128,tolerance_bps:u16,retained_reserve_bps:u16)->Result<()> {
 let a=&mut *ctx.accounts;
 require!(!a.global_params.paused,MayhemError::TradingPaused);
 let now=Clock::get().unwrap().unix_timestamp;
 let last=a.mayhem_state.field_89 as i64;
 let interval=i64::from_le_bytes(a.global_params.reset_middle[9..17].try_into().unwrap());
 if last!=0&&interval!=0 {require!(now>=last+interval,SellError::TradeRateLimit);}
 a.mayhem_state.field_89=now as u64;
 require!(Clock::get().unwrap().unix_timestamp<a.mayhem_state.end_timestamp,SellError::MayhemModeEnded);
 if a.mayhem_state.status!=MayhemStatus::Variant1 {
  require!(a.bonding_curve.real_sol_reserves>=u64::from_le_bytes(a.global_params.preserved_middle_a),SellError::SolReservesTooLow);
  a.mayhem_state.status=MayhemStatus::Variant1;
 }
 let c=&a.bonding_curve;
 let vt=c.virtual_token_reserves as u128;let vs=c.virtual_sol_reserves as u128;
 if vt==0{return Err(math());}
 let scaled=reference.checked_mul(tolerance_bps as u128).ok_or_else(math)?;
 let price=vs*1_000_000_000_000_000u128/vt;let delta=scaled/10_000;
 let low=reference.checked_sub(delta).ok_or_else(math)?;let high=reference.checked_add(delta).ok_or_else(math)?;
 if price<low||price>high{return Err(SellError::PumpCpiSlippage.into());}
 let retained=10_000u16-retained_reserve_bps;
 let tokens=a.mayhem_token_vault.amount as u128;
 let mut output=u64::try_from(vs*tokens/(vt+tokens)).unwrap();
 let cap=u64::from_le_bytes(a.global_params.reset_prefix[8..16].try_into().unwrap());
 if cap!=0 {output=output.min(cap);}
 output=output.min((c.real_sol_reserves as u128*retained as u128/10_000) as u64);
 let input=u64::try_from((output as u128*vt).checked_div(vs-output as u128).unwrap()).unwrap();
 let minimum=output.saturating_sub(1);
 let before_sol=a.sol_vault.lamports();let before_tokens=a.mayhem_token_vault.amount;
 let infos=[a.global.to_account_info(),a.fee_recipient.to_account_info(),a.mint.to_account_info(),a.bonding_curve.to_account_info(),a.associated_bonding_curve.to_account_info(),a.mayhem_token_vault.to_account_info(),a.sol_vault.to_account_info(),a.system_program.to_account_info(),a.creator_vault.to_account_info(),a.token_program.to_account_info(),a.pump_event_authority.to_account_info(),a.pump_program.to_account_info(),a.fee_config.to_account_info(),a.fee_program.to_account_info(),a.bonding_curve_v2.to_account_info(),a.buyback_recipient.to_account_info()];
 let writable=[false,true,false,true,true,true,true,false,true,false,false,false,false,false,false,true];
 let metas=infos.iter().enumerate().map(|(i,info)|if writable[i]{AccountMeta::new(*info.key,i==6)}else{AccountMeta::new_readonly(*info.key,i==6)}).collect();
 let mut data=vec![0x33,0xe6,0x85,0xa4,0x01,0x7f,0x83,0xad];data.extend_from_slice(&input.to_le_bytes());data.extend_from_slice(&minimum.to_le_bytes());
 let bump=[ctx.bumps.sol_vault];let seeds:&[&[u8]]=&[b"sol-vault",&bump];
 invoke_signed(&Instruction{program_id:PUMP_ID,accounts:metas,data},&infos,&[seeds])?;
 a.mayhem_token_vault.reload()?;a.bonding_curve.reload()?;
 let sol=a.sol_vault.lamports()-before_sol;let tokens=before_tokens-a.mayhem_token_vault.amount;
 a.global_params.sol_deployed=a.global_params.sol_deployed.checked_sub(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_56=a.mayhem_state.field_56.checked_sub(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_72=a.mayhem_state.field_72.checked_add(tokens as i128).ok_or_else(math)?;
 let event=SellEvent{side:1,sol_vault:a.sol_vault.key(),mint:a.mint.key(),sol_amount:sol,token_amount:tokens,sol_vault_balance:a.sol_vault.lamports(),token_vault_balance:a.mayhem_token_vault.amount,state_sol_deployed:a.mayhem_state.field_56,state_token_net:a.mayhem_state.field_72,virtual_sol:a.bonding_curve.virtual_sol_reserves,virtual_tokens:a.bonding_curve.virtual_token_reserves,global_sol_deployed:a.global_params.sol_deployed,timestamp:Clock::get()?.unix_timestamp,end_timestamp:a.mayhem_state.end_timestamp,real_sol:a.bonding_curve.real_sol_reserves,real_tokens:a.bonding_curve.real_token_reserves,version:a.global_params.version,retained_reserve_bps,quote_amount:sol,quote_vault_balance:a.sol_vault.lamports(),state_quote_deployed:a.mayhem_state.field_56,virtual_quote:a.bonding_curve.virtual_sol_reserves,global_quote_deployed:a.global_params.sol_deployed,real_quote:a.bonding_curve.real_sol_reserves,quote_mint:Pubkey::default()};
 emit!(event);emit_cpi!(event);Ok(())
}
#[event(discriminator=[0x31,0x48,0x7b,0x2d,0x6e,0x40,0xb0,0x85])]
pub struct SellEvent {
 pub side:u8,pub sol_vault:Pubkey,pub mint:Pubkey,
 pub sol_amount:u64,pub token_amount:u64,pub sol_vault_balance:u64,pub token_vault_balance:u64,
 pub state_sol_deployed:i128,pub state_token_net:i128,pub virtual_sol:u64,pub virtual_tokens:u64,
 pub global_sol_deployed:i128,pub timestamp:i64,pub end_timestamp:i64,pub real_sol:u64,pub real_tokens:u64,
 pub version:u32,pub retained_reserve_bps:u16,pub quote_amount:u64,pub quote_vault_balance:u64,
 pub state_quote_deployed:i128,pub virtual_quote:u64,pub global_quote_deployed:i128,pub real_quote:u64,pub quote_mint:Pubkey,
}
#[error_code]
pub enum SellError {
 #[msg("Too little sol reserves")]SolReservesTooLow=3,
 #[msg("Mayhem mode ended")]MayhemModeEnded=4,
 #[msg("Price impact exceeds slippage tolerance in Pump CPI call")]PumpCpiSlippage=12,
 #[msg("Trade Rate limit")]TradeRateLimit=15,
}
