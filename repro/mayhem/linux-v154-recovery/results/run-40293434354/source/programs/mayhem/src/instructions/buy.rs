//! Legacy buy recovered from original dispatch 0x813f8, parser 0x525f8,
//! handler 0x1bc08 and signed-counter/risk helper 0x2c598.
//! Fixture validation is synthetic and ordinary-signed; no historical prestate claim.
use anchor_lang::prelude::*;
use anchor_lang::solana_program::{instruction::Instruction,program::invoke_signed};
use anchor_spl::token_interface::{Mint,TokenAccount};
use anchor_spl::token_2022::Token2022;
use crate::{GlobalParams,MayhemError};
use crate::state::{MayhemState,MayhemStatus,PUMP_ID};
use super::sell::{SellCurve,SellEvent,SellError};
use crate::checked_program::{CheckedSystemProgram,CheckedSystemProgramBumps,__client_accounts_checked_system_program,__cpi_client_accounts_checked_system_program};

#[derive(Accounts)]
pub struct LegacyBuy<'info> {
 #[account(mut)]pub trader:Signer<'info>,
 #[account(mut,seeds=[b"global-params"],bump,has_one=trader)]pub global_params:Box<Account<'info,GlobalParams>>,
 #[account(mut,seeds=[b"mayhem-state",mint.key().as_ref()],bump)]pub mayhem_state:Box<Account<'info,MayhemState>>,
 pub mint:Box<InterfaceAccount<'info,Mint>>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=sol_vault,associated_token::token_program=mint.to_account_info().owner)]pub mayhem_token_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: Original writable PDA constraint.
 #[account(mut,seeds=[b"sol-vault"],bump)]pub sol_vault:UncheckedAccount<'info>,
 pub system_program:CheckedSystemProgram<'info>,
 pub token_program:Program<'info,Token2022>,
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
 /// CHECK: Pump validates global volume state.
 #[account(mut)]pub global_volume_accumulator:UncheckedAccount<'info>,
 /// CHECK: Pump validates the sol-vault user volume account.
 #[account(mut)]pub user_volume_accumulator:UncheckedAccount<'info>,
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
fn math()->Error {MayhemError::MathOverflow.into()}
pub fn handler(ctx:Context<LegacyBuy>,reference:u128,tolerance_bps:u16,retained_reserve_bps:u16)->Result<()> {
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
 // Price-band check precedes quote construction and the real Pump CPI.
 let c=&a.bonding_curve;
 let vt=c.virtual_token_reserves as u128;let vs=c.virtual_sol_reserves as u128;
 if vt==0{return Err(math());}
 let scaled=reference.checked_mul(tolerance_bps as u128).ok_or_else(math)?;
 let price=vs*1_000_000_000_000_000u128/vt;let delta=scaled/10_000;
 let low=reference.checked_sub(delta).ok_or_else(math)?;let high=reference.checked_add(delta).ok_or_else(math)?;
 if price<low||price>high{return Err(SellError::PumpCpiSlippage.into());}
 let retained=10_000u16-retained_reserve_bps;
 let tokens=a.mayhem_token_vault.amount as u128;
 // The SOL budget is derived from current vault tokens, then constrained by
 // the optional global cap and retained real SOL reserves.
 let mut output=u64::try_from(vs*tokens/(vt+tokens)).unwrap();
 let cap=u64::from_le_bytes(a.global_params.reset_prefix[8..16].try_into().unwrap());
 if cap!=0 {output=output.min(cap);}
 output=output.min((c.real_sol_reserves as u128*retained as u128/10_000) as u64);
 let input=u64::try_from((output as u128*vt).checked_div(vs+output as u128).unwrap()).unwrap().min(c.real_token_reserves);
 let before_sol=a.sol_vault.lamports();let before_tokens=a.mayhem_token_vault.amount;
 let infos=[a.global.to_account_info(),a.fee_recipient.to_account_info(),a.mint.to_account_info(),a.bonding_curve.to_account_info(),a.associated_bonding_curve.to_account_info(),a.mayhem_token_vault.to_account_info(),a.sol_vault.to_account_info(),a.system_program.to_account_info(),a.token_program.to_account_info(),a.creator_vault.to_account_info(),a.pump_event_authority.to_account_info(),a.pump_program.to_account_info(),a.global_volume_accumulator.to_account_info(),a.user_volume_accumulator.to_account_info(),a.fee_config.to_account_info(),a.fee_program.to_account_info(),a.bonding_curve_v2.to_account_info(),a.buyback_recipient.to_account_info()];
 let writable=[false,true,false,true,true,true,true,false,false,true,false,false,true,true,false,false,false,true];
 let metas=infos.iter().enumerate().map(|(i,info)|if writable[i]{AccountMeta::new(*info.key,i==6)}else{AccountMeta::new_readonly(*info.key,i==6)}).collect();
 let mut data=vec![0x66,0x06,0x3d,0x12,0x01,0xda,0xeb,0xea];data.extend_from_slice(&input.to_le_bytes());data.extend_from_slice(&output.to_le_bytes());data.push(0);
 let bump=[ctx.bumps.sol_vault];let seeds:&[&[u8]]=&[b"sol-vault",&bump];
 require!(invoke_signed(&Instruction{program_id:PUMP_ID,accounts:metas,data},&infos,&[seeds]).is_ok(),BuyError::PumpCpiFailed);
 a.mayhem_token_vault.reload()?;a.bonding_curve.reload()?;
 let sol=before_sol-a.sol_vault.lamports();let tokens=a.mayhem_token_vault.amount-before_tokens;
 a.global_params.sol_deployed=a.global_params.sol_deployed.checked_add(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_56=a.mayhem_state.field_56.checked_add(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_72=a.mayhem_state.field_72.checked_sub(tokens as i128).ok_or_else(math)?;
 // Original tests signed positivity, then compares the low u64 limb with
 // a strict upper bound. Preserve that truncation even for counters > u64::MAX.
 if a.global_params.sol_deployed>0 {require_gt!(u64::from_le_bytes(a.global_params.reset_prefix[24..32].try_into().unwrap()),a.global_params.sol_deployed as u64,BuyError::OverallRiskExceeded);}
 if a.mayhem_state.field_56>0 {require_gt!(u64::from_le_bytes(a.global_params.reset_prefix[32..40].try_into().unwrap()),a.mayhem_state.field_56 as u64,BuyError::CoinRiskExceeded);}
 let event=SellEvent{side:0,sol_vault:a.sol_vault.key(),mint:a.mint.key(),sol_amount:sol,token_amount:tokens,sol_vault_balance:a.sol_vault.lamports(),token_vault_balance:a.mayhem_token_vault.amount,state_sol_deployed:a.mayhem_state.field_56,state_token_net:a.mayhem_state.field_72,virtual_sol:a.bonding_curve.virtual_sol_reserves,virtual_tokens:a.bonding_curve.virtual_token_reserves,global_sol_deployed:a.global_params.sol_deployed,timestamp:Clock::get()?.unix_timestamp,end_timestamp:a.mayhem_state.end_timestamp,real_sol:a.bonding_curve.real_sol_reserves,real_tokens:a.bonding_curve.real_token_reserves,version:a.global_params.version,retained_reserve_bps,quote_amount:sol,quote_vault_balance:a.sol_vault.lamports(),state_quote_deployed:a.mayhem_state.field_56,virtual_quote:a.bonding_curve.virtual_sol_reserves,global_quote_deployed:a.global_params.sol_deployed,real_quote:a.bonding_curve.real_sol_reserves,quote_mint:Pubkey::default()};
 emit!(event);emit_cpi!(event);Ok(())
}
#[error_code]
pub enum BuyError {
 #[msg("Overall risk tolerance exceeded")]OverallRiskExceeded=6,
 #[msg("Per coin risk tolerance exceeded")]CoinRiskExceeded=7,
 #[msg("Pump CPI call failed")]PumpCpiFailed=8,
}
