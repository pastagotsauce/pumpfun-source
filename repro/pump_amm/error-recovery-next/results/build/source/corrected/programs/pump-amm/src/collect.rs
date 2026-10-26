use crate::*;
use anchor_spl::token_interface::TokenInterface;
#[event_cpi]
#[derive(Accounts)]
pub struct CollectCoinCreatorFee<'info> {
 pub quote_mint: Box<InterfaceAccount<'info,Mint>>,
 pub quote_token_program: Interface<'info,TokenInterface>,
 /// CHECK: the destination authority is this key; migrated Fee-owned accounts are rejected.
 pub coin_creator: UncheckedAccount<'info>,
 /// CHECK: PDA constrained by creator-vault seeds.
 #[account(seeds=[b"creator_vault",coin_creator.key().as_ref()],bump)]
 pub coin_creator_vault_authority: UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=quote_mint,associated_token::authority=coin_creator_vault_authority,associated_token::token_program=quote_token_program)]
 pub coin_creator_vault_ata: Box<InterfaceAccount<'info,TokenAccount>>,
 #[account(mut,token::mint=quote_mint,token::authority=coin_creator,token::token_program=quote_token_program)]
 pub coin_creator_token_account: Box<InterfaceAccount<'info,TokenAccount>>,
}
pub fn execute(ctx:Context<CollectCoinCreatorFee>)->Result<()> {
 let a=&ctx.accounts;
 require!(*a.coin_creator.owner != crate::trade::FEE_OWNER,PumpAmmError::CreatorVaultMigratedToSharingConfig);
 let amount=a.coin_creator_vault_ata.amount;if amount==0 {msg!("No coin creator fee to collect");return Ok(())}
 let creator=a.coin_creator.key();let bump=[ctx.bumps.coin_creator_vault_authority];let seeds:&[&[u8]]=&[b"creator_vault",creator.as_ref(),&bump];
 token_interface::transfer_checked(CpiContext::new_with_signer(a.quote_token_program.to_account_info(),token_interface::TransferChecked{from:a.coin_creator_vault_ata.to_account_info(),mint:a.quote_mint.to_account_info(),to:a.coin_creator_token_account.to_account_info(),authority:a.coin_creator_vault_authority.to_account_info()},&[seeds]),amount,a.quote_mint.decimals)?;
 let event=CollectCoinCreatorFeeEvent{timestamp:Clock::get()?.unix_timestamp,coin_creator:creator,coin_creator_fee:amount,coin_creator_vault_ata:a.coin_creator_vault_ata.key(),coin_creator_token_account:a.coin_creator_token_account.key()};emit!(event.clone());emit_cpi!(event);Ok(())
}
#[event]
#[derive(Clone)]
pub struct CollectCoinCreatorFeeEvent{pub timestamp:i64,pub coin_creator:Pubkey,pub coin_creator_fee:u64,pub coin_creator_vault_ata:Pubkey,pub coin_creator_token_account:Pubkey}
