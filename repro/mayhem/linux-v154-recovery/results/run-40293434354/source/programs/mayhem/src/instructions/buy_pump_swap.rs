//! Independently reconstructed PumpSwap handler and account constraints.
//! Byte-checked original parser 0x46378 (buy), 0x4cc98 (sell).
use anchor_lang::prelude::*;
use anchor_spl::associated_token::AssociatedToken;
use anchor_spl::token_interface::{Mint,TokenAccount,TokenInterface};
use anchor_spl::token_2022::Token2022;
use crate::{GlobalParams,MayhemError};
use crate::state::MayhemStatus;
use anchor_lang::solana_program::{instruction::Instruction,program::invoke_signed};
use super::sell::{SellEvent,SellError};
use super::buy::BuyError;
use super::pump_swap_types::{SwapPool,SwapGlobalConfig,AMM_ID,PumpSwapError};
const WSOL:Pubkey=pubkey!("So11111111111111111111111111111111111111112");
use crate::state::MayhemState;
use crate::checked_program::{CheckedSystemProgram,CheckedSystemProgramBumps,__client_accounts_checked_system_program,__cpi_client_accounts_checked_system_program};
const SPL_TOKEN_ID:Pubkey=pubkey!("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
#[derive(Accounts)]
pub struct BuyPumpSwap<'info> {
 #[account(mut)]pub trader:Signer<'info>,
 #[account(mut,seeds=[b"global-params"],bump,has_one=trader)]pub global_params:Box<Account<'info,GlobalParams>>,
 #[account(mut,seeds=[b"mayhem-state",mint.key().as_ref()],bump)]pub mayhem_state:Box<Account<'info,MayhemState>>,
 pub mint:Box<InterfaceAccount<'info,Mint>>,
 #[account(mut,associated_token::mint=mint,associated_token::authority=sol_vault,associated_token::token_program=mint.to_account_info().owner)]
 pub mayhem_token_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 #[account(init_if_needed,payer=trader,associated_token::mint=quote_mint,associated_token::authority=sol_vault,associated_token::token_program=quote_token_program)]
 pub mayhem_quote_vault:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: original PDA+mut only; no SystemAccount ownership check.
 #[account(mut,seeds=[b"sol-vault"],bump)]pub sol_vault:UncheckedAccount<'info>,
 pub system_program:CheckedSystemProgram<'info>,
 // Original parses Interface then applies address constraint 2012 at 0x49568.
 #[account(address=SPL_TOKEN_ID)]pub quote_token_program:Interface<'info,TokenInterface>,
 pub base_token_program:Program<'info,Token2022>,
 pub associated_token_program:Program<'info,AssociatedToken>,
 // Original has no pool seeds or has_one checks, only typed owner/discriminator + mut.
 #[account(mut)]pub pool:Box<Account<'info,SwapPool>>,
 pub global_config:Box<Account<'info,SwapGlobalConfig>>,
 /// CHECK: original consumes AccountInfo directly at 0x47560, no Mint deserialize.
 pub quote_mint:UncheckedAccount<'info>,
 #[account(mut)]pub pool_base_token_account:Box<InterfaceAccount<'info,TokenAccount>>,
 #[account(mut)]pub pool_quote_token_account:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: original mut only; membership checked by AMM CPI.
 #[account(mut)]pub protocol_fee_recipient:UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=quote_mint,associated_token::authority=protocol_fee_recipient,associated_token::token_program=quote_token_program)]
 pub protocol_fee_recipient_token_account:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: original unchecked, no outer seed check.
 pub pump_swap_event_authority:UncheckedAccount<'info>,
 /// CHECK: original fixed address only, not Program<...>.
 #[account(address=AMM_ID)]pub pump_swap_program:UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=quote_mint,associated_token::authority=coin_creator_vault_authority,associated_token::token_program=quote_token_program)]
 pub coin_creator_vault_ata:Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: original unchecked, actual AMM CPI validates authority.
 pub coin_creator_vault_authority:UncheckedAccount<'info>,
 /// CHECK: original unchecked + mut, buy only.
 #[account(mut)]pub global_volume_accumulator:UncheckedAccount<'info>,
 /// CHECK: original unchecked + mut, buy only.
 #[account(mut)]pub user_volume_accumulator:UncheckedAccount<'info>,
 /// CHECK: original unchecked.
 pub fee_config:UncheckedAccount<'info>,
 /// CHECK: original unchecked.
 pub fee_program:UncheckedAccount<'info>,
 /// CHECK: original Mayhem-derived event authority.
 #[account(seeds=[b"__event_authority"],bump)]pub event_authority:UncheckedAccount<'info>,
 pub program:Program<'info,crate::program::MayhemRecovered>,
 /// CHECK: original PDA is derived under MAYHEM; not AMM; no mut/owner check.
 #[account(seeds=[b"pool-v2",mint.key().as_ref()],bump)]pub pool_v2:UncheckedAccount<'info>,
 /// CHECK: original unchecked and read-only.
 pub buyback_recipient:UncheckedAccount<'info>,
 /// CHECK: original unchecked + mut; actual AMM CPI validates ATA.
 #[account(mut)]pub buyback_recipient_ata:UncheckedAccount<'info>,
}

fn math()->Error {MayhemError::MathOverflow.into()}
pub fn handler(ctx:Context<BuyPumpSwap>,reference:u128,tolerance_bps:u16,retained_reserve_bps:u16)->Result<()> {
 let a=&mut *ctx.accounts;
 let native=a.quote_mint.key()==WSOL;
 let native_accounting=native||a.quote_mint.key()==Pubkey::default();
 require!(!a.global_params.paused,MayhemError::TradingPaused);
 let now=Clock::get().unwrap().unix_timestamp;
 let last=a.mayhem_state.field_89 as i64;
 let interval=i64::from_le_bytes(a.global_params.reset_middle[9..17].try_into().unwrap());
 if last!=0&&interval!=0 {require!(now>=last+interval,SellError::TradeRateLimit);}
 a.mayhem_state.field_89=now as u64;
 let effective_quote=u64::try_from((a.pool_quote_token_account.amount as i128).checked_add(a.pool.virtual_quote_reserves).ok_or_else(math)?).map_err(|_|math())?;
 require!(Clock::get().unwrap().unix_timestamp<a.mayhem_state.end_timestamp,SellError::MayhemModeEnded);
 if a.mayhem_state.status!=MayhemStatus::Variant1 {
  require!(effective_quote>=if native_accounting{u64::from_le_bytes(a.global_params.preserved_middle_a)}else{u64::from_le_bytes(a.global_params.reset_stable_suffix[0..8].try_into().unwrap())},SellError::SolReservesTooLow);
  a.mayhem_state.status=MayhemStatus::Variant1;
 }
 let vt=a.pool_base_token_account.amount as u128;let vs=effective_quote as u128;
 if vt==0{return Err(math());}
 let scaled=reference.checked_mul(tolerance_bps as u128).ok_or_else(math)?;
 let price=vs*1_000_000_000_000_000u128/vt;let delta=scaled/10_000;
 let low=reference.checked_sub(delta).ok_or_else(math)?;let high=reference.checked_add(delta).ok_or_else(math)?;
 if price<low||price>high{return Err(SellError::PumpCpiSlippage.into());}
 let retained=10_000u16-retained_reserve_bps;
 let tokens=a.mayhem_token_vault.amount as u128;
 let mut output=u64::try_from(vs*tokens/(vt+tokens)).unwrap();
 let cap=if native_accounting{u64::from_le_bytes(a.global_params.reset_prefix[8..16].try_into().unwrap())}else{u64::from_le_bytes(a.global_params.reset_stable_prefix[0..8].try_into().unwrap())};
 if cap!=0 {output=output.min(cap);}
 output=output.min((effective_quote as u128*retained as u128/10_000) as u64);
 let input=u64::try_from((output as u128*vt).checked_div(vs+output as u128).ok_or(PumpSwapError::PumpSwapCpiMathOverflow).unwrap()).unwrap();
 let before_sol=if native{a.sol_vault.lamports()}else{a.mayhem_quote_vault.amount};let before_tokens=a.mayhem_token_vault.amount;
 let bump=[ctx.bumps.sol_vault];let seeds:&[&[u8]]=&[b"sol-vault",&bump];
 if native {
  let ix=anchor_lang::solana_program::system_instruction::transfer(&a.sol_vault.key(),&a.mayhem_quote_vault.key(),output);
  invoke_signed(&ix,&[a.sol_vault.to_account_info(),a.mayhem_quote_vault.to_account_info(),a.system_program.to_account_info()],&[seeds])?;
  invoke_signed(&Instruction{program_id:a.quote_token_program.key(),accounts:vec![AccountMeta::new(a.mayhem_quote_vault.key(),false)],data:vec![17]},&[a.mayhem_quote_vault.to_account_info(),a.quote_token_program.to_account_info()],&[seeds])?;
  a.mayhem_quote_vault.reload()?;
 }
 let infos=[a.pool.to_account_info(),a.sol_vault.to_account_info(),a.global_config.to_account_info(),a.mint.to_account_info(),a.quote_mint.to_account_info(),a.mayhem_token_vault.to_account_info(),a.mayhem_quote_vault.to_account_info(),a.pool_base_token_account.to_account_info(),a.pool_quote_token_account.to_account_info(),a.protocol_fee_recipient.to_account_info(),a.protocol_fee_recipient_token_account.to_account_info(),a.base_token_program.to_account_info(),a.quote_token_program.to_account_info(),a.system_program.to_account_info(),a.associated_token_program.to_account_info(),a.pump_swap_event_authority.to_account_info(),a.pump_swap_program.to_account_info(),a.coin_creator_vault_ata.to_account_info(),a.coin_creator_vault_authority.to_account_info(),a.global_volume_accumulator.to_account_info(),a.user_volume_accumulator.to_account_info(),a.fee_config.to_account_info(),a.fee_program.to_account_info(),a.buyback_recipient.to_account_info(),a.buyback_recipient_ata.to_account_info()];
 let writable=[true,true,false,false,false,true,true,true,true,false,true,false,false,false,false,false,false,true,false,true,true,false,false,false,true];
 let metas=infos.iter().enumerate().map(|(i,info)|if i>=23{if info.is_writable{AccountMeta::new(*info.key,info.is_signer)}else{AccountMeta::new_readonly(*info.key,info.is_signer)}}else if writable[i]{AccountMeta::new(*info.key,i==1)}else{AccountMeta::new_readonly(*info.key,i==1)}).collect();
 let mut data=vec![0x66,0x06,0x3d,0x12,0x01,0xda,0xeb,0xea];data.extend_from_slice(&input.to_le_bytes());data.extend_from_slice(&output.to_le_bytes());data.push(0);
 require!(invoke_signed(&Instruction{program_id:AMM_ID,accounts:metas,data},&infos,&[seeds]).is_ok(),PumpSwapError::PumpSwapCpiFailed);
 if native {invoke_signed(&Instruction{program_id:a.quote_token_program.key(),accounts:vec![AccountMeta::new(a.mayhem_quote_vault.key(),false),AccountMeta::new(a.sol_vault.key(),false),AccountMeta::new_readonly(a.sol_vault.key(),true)],data:vec![9]},&[a.mayhem_quote_vault.to_account_info(),a.sol_vault.to_account_info(),a.sol_vault.to_account_info(),a.quote_token_program.to_account_info()],&[seeds])?;}
 a.mayhem_token_vault.reload()?;a.pool_base_token_account.reload()?;a.pool_quote_token_account.reload()?;if !native{a.mayhem_quote_vault.reload()?;}
 let after_quote=if native{a.sol_vault.lamports()}else{a.mayhem_quote_vault.amount};
 let sol=before_sol-after_quote;let tokens=a.mayhem_token_vault.amount-before_tokens;
 if native_accounting{a.global_params.sol_deployed=a.global_params.sol_deployed.checked_add(sol as i128).ok_or_else(math)?;}else{a.global_params.stable_deployed=a.global_params.stable_deployed.checked_add(sol as i128).ok_or_else(math)?;}
 a.mayhem_state.field_56=a.mayhem_state.field_56.checked_add(sol as i128).ok_or_else(math)?;
 a.mayhem_state.field_72=a.mayhem_state.field_72.checked_sub(tokens as i128).ok_or_else(math)?;
 let global_deployed=if native_accounting{a.global_params.sol_deployed}else{a.global_params.stable_deployed};
 let overall_limit=if native_accounting{u64::from_le_bytes(a.global_params.reset_prefix[24..32].try_into().unwrap())}else{u64::from_le_bytes(a.global_params.reset_stable_prefix[8..16].try_into().unwrap())};
 let coin_limit=if native_accounting{u64::from_le_bytes(a.global_params.reset_prefix[32..40].try_into().unwrap())}else{u64::from_le_bytes(a.global_params.reset_stable_prefix[16..24].try_into().unwrap())};
 if global_deployed>0 {require_gt!(overall_limit,global_deployed as u64,BuyError::OverallRiskExceeded);}
 if a.mayhem_state.field_56>0 {require_gt!(coin_limit,a.mayhem_state.field_56 as u64,BuyError::CoinRiskExceeded);}
 let event=SellEvent{side:0,sol_vault:a.sol_vault.key(),mint:a.mint.key(),sol_amount:if native{sol}else{0},token_amount:tokens,sol_vault_balance:if native{a.sol_vault.lamports()}else{0},token_vault_balance:a.mayhem_token_vault.amount,state_sol_deployed:if native{a.mayhem_state.field_56}else{0},state_token_net:a.mayhem_state.field_72,virtual_sol:if native{a.pool_quote_token_account.amount}else{0},virtual_tokens:a.pool_base_token_account.amount,global_sol_deployed:if native{a.global_params.sol_deployed}else{0},timestamp:Clock::get()?.unix_timestamp,end_timestamp:a.mayhem_state.end_timestamp,real_sol:if native{a.pool_quote_token_account.amount}else{0},real_tokens:a.pool_base_token_account.amount,version:a.global_params.version,retained_reserve_bps,quote_amount:sol,quote_vault_balance:after_quote,state_quote_deployed:a.mayhem_state.field_56,virtual_quote:a.pool_quote_token_account.amount,global_quote_deployed:if native_accounting{a.global_params.sol_deployed}else{a.global_params.stable_deployed},real_quote:a.pool_quote_token_account.amount,quote_mint:if native{Pubkey::default()}else{a.quote_mint.key()}};
 emit!(event);emit_cpi!(event);Ok(())
}
