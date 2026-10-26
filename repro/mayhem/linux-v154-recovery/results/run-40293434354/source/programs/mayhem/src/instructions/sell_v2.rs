//! SellV2 recovered from wrapper 0x81738, parser 0x61b40 and handler 0x26db8.
use anchor_lang::prelude::*;
use anchor_lang::solana_program::{instruction::Instruction,program::invoke_signed};
use anchor_spl::token_interface::{Mint,TokenAccount,TokenInterface};
use anchor_spl::token_2022::Token2022;
use crate::{GlobalParams,MayhemError};
use crate::state::{MayhemState,MayhemStatus,PUMP_ID};
use crate::checked_program::{CheckedSystemProgram,CheckedSystemProgramBumps,__client_accounts_checked_system_program,__cpi_client_accounts_checked_system_program};

use anchor_spl::associated_token::AssociatedToken;
use super::sell::{SellCurve,SellEvent,SellError};
use super::buy::BuyError;
const WSOL:Pubkey=pubkey!("So11111111111111111111111111111111111111112");
#[derive(Accounts)]
pub struct SellV2<'info> {
 #[account(mut)]pub trader:Signer<'info>,
 #[account(mut,seeds=[b"global-params"],bump,has_one=trader)]pub global_params:Box<Account<'info,GlobalParams>>,
 #[account(mut,seeds=[b"mayhem-state",mint.key().as_ref()],bump)]pub mayhem_state:Box<Account<'info,MayhemState>>,
 pub mint:Box<InterfaceAccount<'info,Mint>>,
 /// CHECK: Original unchecked quote account; ATA owner and Pump CPI constrain its use.
 pub quote_mint:UncheckedAccount<'info>,
 pub associated_token_program:Program<'info,AssociatedToken>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=sol_vault,associated_token::token_program=mint.to_account_info().owner)]pub mayhem_base_token_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 #[account(mut,associated_token::mint=quote_mint,associated_token::authority=sol_vault,associated_token::token_program=quote_mint.to_account_info().owner)]pub mayhem_quote_token_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: Original writable PDA.
 #[account(mut,seeds=[b"sol-vault"],bump)]pub sol_vault:UncheckedAccount<'info>,
 pub system_program:CheckedSystemProgram<'info>,
 pub token_program:Program<'info,Token2022>,
 pub quote_token_program:Interface<'info,TokenInterface>,
 /// CHECK: Passed through to Pump.
 pub global:UncheckedAccount<'info>,
 #[account(mut,seeds=[b"bonding-curve",mint.key().as_ref()],bump,seeds::program=PUMP_ID)]pub bonding_curve:Box<Account<'info,SellCurve>>,
 /// CHECK: Pump validates quote ATA.
 #[account(mut)]pub associated_quote_bonding_curve:UncheckedAccount<'info>,
 /// CHECK: Pump validates recipient membership.
 #[account(mut)]pub fee_recipient:UncheckedAccount<'info>,
 /// CHECK: Pump validates recipient ATA.
 #[account(mut)]pub fee_recipient_ata:UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=bonding_curve,associated_token::token_program=mint.to_account_info().owner)]pub associated_base_bonding_curve:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: Pump validates creator PDA.
 #[account(mut)]pub creator_vault:UncheckedAccount<'info>,
 /// CHECK: Pump validates creator ATA.
 #[account(mut)]pub associated_creator_vault:UncheckedAccount<'info>,
 /// CHECK: Pump validates sharing config.
 pub sharing_config:UncheckedAccount<'info>,
 /// CHECK: Pump event authority.
 pub pump_event_authority:UncheckedAccount<'info>,
 /// CHECK: Original fixed address.
 #[account(address=PUMP_ID)]pub pump_program:UncheckedAccount<'info>,
 /// CHECK: Pump validates volume PDA.
 #[account(mut)]pub user_volume_accumulator:UncheckedAccount<'info>,
 /// CHECK: Pump validates volume ATA.
 #[account(mut)]pub associated_user_volume_accumulator:UncheckedAccount<'info>,
 /// CHECK: Pump validates fee config.
 pub fee_config:UncheckedAccount<'info>,
 /// CHECK: Pump validates fee program.
 pub fee_program:UncheckedAccount<'info>,
 /// CHECK: Original event PDA.
 #[account(seeds=[b"__event_authority"],bump)]pub event_authority:UncheckedAccount<'info>,
 pub program:Program<'info,crate::program::MayhemRecovered>,
 /// CHECK: Pump validates buyback recipient.
 #[account(mut)]pub buyback_recipient:UncheckedAccount<'info>,
 /// CHECK: Pump validates buyback ATA.
 #[account(mut)]pub buyback_recipient_ata:UncheckedAccount<'info>,
}
fn math()->Error {MayhemError::MathOverflow.into()}
pub fn handler(ctx:Context<SellV2>,reference:u128,tolerance_bps:u16,retained_reserve_bps:u16)->Result<()> {
 let a=&mut *ctx.accounts;
 let native=a.quote_mint.key()==WSOL;
 let native_accounting=native||a.quote_mint.key()==Pubkey::default();
 require!(!a.global_params.paused,MayhemError::TradingPaused);
 let now=Clock::get().unwrap().unix_timestamp;
 let last=a.mayhem_state.field_89 as i64;
 let interval=i64::from_le_bytes(a.global_params.reset_middle[9..17].try_into().unwrap());
 if last!=0&&interval!=0 {require!(now>=last+interval,SellError::TradeRateLimit);}
 a.mayhem_state.field_89=now as u64;
 require!(Clock::get().unwrap().unix_timestamp<a.mayhem_state.end_timestamp,SellError::MayhemModeEnded);
 if a.mayhem_state.status!=MayhemStatus::Variant1 {
  require!(a.bonding_curve.real_sol_reserves>=if native_accounting{u64::from_le_bytes(a.global_params.preserved_middle_a)}else{u64::from_le_bytes(a.global_params.reset_stable_suffix[0..8].try_into().unwrap())},SellError::SolReservesTooLow);
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
 let tokens=a.mayhem_base_token_vault.amount as u128;
 let mut output=u64::try_from(vs*tokens/(vt+tokens)).unwrap();
 let cap=if native_accounting{u64::from_le_bytes(a.global_params.reset_prefix[8..16].try_into().unwrap())}else{u64::from_le_bytes(a.global_params.reset_stable_prefix[0..8].try_into().unwrap())};
 if cap!=0 {output=output.min(cap);}
 output=output.min((c.real_sol_reserves as u128*retained as u128/10_000) as u64);
 let input=u64::try_from((output as u128*vt).checked_div(vs-output as u128).unwrap()).unwrap();
 let minimum=output.saturating_sub(1);
 let before_sol=if native{a.sol_vault.lamports()}else{a.mayhem_quote_token_vault.amount};let before_tokens=a.mayhem_base_token_vault.amount;
 let infos=[a.global.to_account_info(),a.mint.to_account_info(),a.quote_mint.to_account_info(),a.token_program.to_account_info(),a.quote_token_program.to_account_info(),a.associated_token_program.to_account_info(),a.fee_recipient.to_account_info(),a.fee_recipient_ata.to_account_info(),a.buyback_recipient.to_account_info(),a.buyback_recipient_ata.to_account_info(),a.bonding_curve.to_account_info(),a.associated_base_bonding_curve.to_account_info(),a.associated_quote_bonding_curve.to_account_info(),a.sol_vault.to_account_info(),a.mayhem_base_token_vault.to_account_info(),a.mayhem_quote_token_vault.to_account_info(),a.creator_vault.to_account_info(),a.associated_creator_vault.to_account_info(),a.sharing_config.to_account_info(),a.user_volume_accumulator.to_account_info(),a.associated_user_volume_accumulator.to_account_info(),a.fee_config.to_account_info(),a.fee_program.to_account_info(),a.system_program.to_account_info(),a.pump_event_authority.to_account_info(),a.pump_program.to_account_info()];
 let writable=[false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,false,true,true,false,false,false,false,false];
 let metas=infos.iter().enumerate().map(|(i,info)|if writable[i]{AccountMeta::new(*info.key,i==13)}else{AccountMeta::new_readonly(*info.key,i==13)}).collect();
 let mut data=vec![0x5d,0xf6,0x82,0x3c,0xe7,0xe9,0x40,0xb2];data.extend_from_slice(&input.to_le_bytes());data.extend_from_slice(&minimum.to_le_bytes());
 let bump=[ctx.bumps.sol_vault];let seeds:&[&[u8]]=&[b"sol-vault",&bump];
 require!(invoke_signed(&Instruction{program_id:PUMP_ID,accounts:metas,data},&infos,&[seeds]).is_ok(),BuyError::PumpCpiFailed);
 a.mayhem_base_token_vault.reload()?;a.bonding_curve.reload()?;if !native{a.mayhem_quote_token_vault.reload()?;}
 let after_quote=if native{a.sol_vault.lamports()}else{a.mayhem_quote_token_vault.amount};
 let sol=after_quote-before_sol;let tokens=before_tokens-a.mayhem_base_token_vault.amount;
 if native_accounting{a.global_params.sol_deployed=a.global_params.sol_deployed.checked_sub(sol as i128).ok_or_else(math)?;}else{a.global_params.stable_deployed=a.global_params.stable_deployed.checked_sub(sol as i128).ok_or_else(math)?;}
 a.mayhem_state.field_56=a.mayhem_state.field_56.checked_sub(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_72=a.mayhem_state.field_72.checked_add(tokens as i128).ok_or_else(math)?;
 let event=SellEvent{side:1,sol_vault:a.sol_vault.key(),mint:a.mint.key(),sol_amount:if native{sol}else{0},token_amount:tokens,sol_vault_balance:if native{a.sol_vault.lamports()}else{0},token_vault_balance:a.mayhem_base_token_vault.amount,state_sol_deployed:if native{a.mayhem_state.field_56}else{0},state_token_net:a.mayhem_state.field_72,virtual_sol:if native{a.bonding_curve.virtual_sol_reserves}else{0},virtual_tokens:a.bonding_curve.virtual_token_reserves,global_sol_deployed:if native{a.global_params.sol_deployed}else{0},timestamp:Clock::get()?.unix_timestamp,end_timestamp:a.mayhem_state.end_timestamp,real_sol:if native{a.bonding_curve.real_sol_reserves}else{0},real_tokens:a.bonding_curve.real_token_reserves,version:a.global_params.version,retained_reserve_bps,quote_amount:sol,quote_vault_balance:after_quote,state_quote_deployed:a.mayhem_state.field_56,virtual_quote:a.bonding_curve.virtual_sol_reserves,global_quote_deployed:if native_accounting{a.global_params.sol_deployed}else{a.global_params.stable_deployed},real_quote:a.bonding_curve.real_sol_reserves,quote_mint:if native{Pubkey::default()}else{a.quote_mint.key()}};
 emit!(event);emit_cpi!(event);Ok(())
}
