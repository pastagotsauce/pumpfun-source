use crate::*;
use anchor_spl::token_interface::TokenInterface;
#[derive(Accounts)]
pub struct ClaimCashback<'info> {
    /// CHECK: Destination authority and accumulator seed; no signature required.
    #[account(mut)] pub user: UncheckedAccount<'info>,
    #[account(mut,seeds=[b"user_volume_accumulator",user.key().as_ref()],bump)]
    pub user_volume_accumulator: Account<'info,UserVolumeAccumulator>,
    pub quote_mint: Box<InterfaceAccount<'info,Mint>>,
    pub quote_token_program: Interface<'info,TokenInterface>,
    #[account(mut,associated_token::mint=quote_mint,associated_token::authority=user_volume_accumulator,associated_token::token_program=quote_token_program)]
    pub user_volume_accumulator_wsol_token_account: Box<InterfaceAccount<'info,TokenAccount>>,
    #[account(mut,token::mint=quote_mint,token::authority=user,token::token_program=quote_token_program)]
    pub user_wsol_token_account: Box<InterfaceAccount<'info,TokenAccount>>,
    pub system_program: Program<'info,System>,
    /// CHECK: Anchor event authority PDA.
    #[account(seeds=[b"__event_authority"],bump)]
    pub event_authority:UncheckedAccount<'info>,
    pub program:Program<'info,crate::program::PumpAmmRecovered>,
}
pub fn claim(ctx:Context<ClaimCashback>)->Result<()> {
    let timestamp=Clock::get()?.unix_timestamp;
    let amount=ctx.accounts.user_volume_accumulator_wsol_token_account.amount;
    let user=ctx.accounts.user.key();let bump=[ctx.bumps.user_volume_accumulator];
    let seeds:&[&[u8]]=&[b"user_volume_accumulator",user.as_ref(),&bump];
    if amount>0 {token_interface::transfer_checked(CpiContext::new_with_signer(ctx.accounts.quote_token_program.to_account_info(),token_interface::TransferChecked{from:ctx.accounts.user_volume_accumulator_wsol_token_account.to_account_info(),mint:ctx.accounts.quote_mint.to_account_info(),to:ctx.accounts.user_wsol_token_account.to_account_info(),authority:ctx.accounts.user_volume_accumulator.to_account_info()},&[seeds]),amount,ctx.accounts.quote_mint.decimals)?;}
    let u=&mut ctx.accounts.user_volume_accumulator;
    u.total_cashback_claimed=u.total_cashback_claimed.checked_add(amount).ok_or(error!(PumpAmmError::Overflow))?;
    let event=ClaimCashbackEvent{user,amount,timestamp,total_claimed:u.total_cashback_claimed,total_cashback_earned:u.cashback_earned};emit!(event.clone());emit_cpi!(event);Ok(())
}
#[event]
#[derive(Clone)]
pub struct ClaimCashbackEvent{pub user:Pubkey,pub amount:u64,pub timestamp:i64,pub total_claimed:u64,pub total_cashback_earned:u64}
