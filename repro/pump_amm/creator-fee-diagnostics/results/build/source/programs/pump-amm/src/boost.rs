use crate::*;
use anchor_spl::{associated_token::AssociatedToken, token_interface::TokenInterface};
#[event_cpi]
#[derive(Accounts)]
pub struct InitBoost<'info> {
    #[account(mut,has_one=base_mint @ PumpAmmError::InvalidBaseMint,has_one=quote_mint @ PumpAmmError::InvalidQuoteMint,has_one=pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount,has_one=pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    #[account(seeds=[b"global_config"],bump)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    #[account(mut)]
    pub creator: Signer<'info>,
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    /// CHECK: PDA authority constrained by seeds.
    #[account(seeds=[b"boost_vault",pool.key().as_ref()],bump)]
    pub boost_vault_authority: UncheckedAccount<'info>,
    #[account(init_if_needed,payer=creator,associated_token::mint=quote_mint,associated_token::authority=boost_vault_authority,associated_token::token_program=quote_token_program)]
    pub boost_vault: Box<InterfaceAccount<'info, TokenAccount>>,
    pub quote_token_program: Interface<'info, TokenInterface>,
    pub system_program: Program<'info, System>,
    pub associated_token_program: Program<'info, AssociatedToken>,
}
pub fn execute(ctx: Context<InitBoost>) -> Result<()> {
    let a = &mut *ctx.accounts;
    let pump = crate::trade::PUMP;
    let base = a.base_mint.key();
    let authority = Pubkey::find_program_address(&[b"pool-authority", base.as_ref()], &pump).0;
    let effective = a
        .pool
        .protocol_fees
        .checked_add(a.pool.creator_fees)
        .and_then(|fees| a.pool.virtual_quote_reserves.checked_add(fees as i128));
    if a.creator.key() != authority
        || effective.map_or(false, |x| x != 0)
        || !a.global_config.boost_enabled
    {
        return Ok(());
    }
    let q = a.pool_quote_token_account.amount;
    let amount = u64::try_from(
        (a.pool_base_token_account.amount as u128) * (q as u128) / 1_000_000_000_000_000u128,
    )
    .map_err(|_| error!(PumpAmmError::Truncation))?;
    if amount == 0 || amount >= q {
        return Ok(());
    }
    let p = &a.pool;
    let index = p.index.to_le_bytes();
    let bump = [p.pool_bump];
    let seeds: &[&[u8]] = &[
        b"pool",
        &index,
        p.creator.as_ref(),
        p.base_mint.as_ref(),
        p.quote_mint.as_ref(),
        &bump,
    ];
    token_interface::transfer_checked(
        CpiContext::new_with_signer(
            a.quote_token_program.to_account_info(),
            token_interface::TransferChecked {
                from: a.pool_quote_token_account.to_account_info(),
                mint: a.quote_mint.to_account_info(),
                to: a.boost_vault.to_account_info(),
                authority: a.pool.to_account_info(),
            },
            &[seeds],
        ),
        amount,
        a.quote_mint.decimals,
    )?;
    a.pool.virtual_quote_reserves = amount as i128;
    a.pool_quote_token_account.reload()?;
    let event = InitBoostEvent {
        timestamp: Clock::get()?.unix_timestamp,
        mint: base,
        bonding_curve: Pubkey::find_program_address(&[b"bonding-curve", base.as_ref()], &pump).0,
        pool: a.pool.key(),
        virtual_quote_reserves: amount as i128,
        real_quote_reserves_after: a.pool_quote_token_account.amount,
    };
    emit!(event.clone());
    emit_cpi!(event);
    Ok(())
}
#[event]
#[derive(Clone)]
pub struct InitBoostEvent {
    pub timestamp: i64,
    pub mint: Pubkey,
    pub bonding_curve: Pubkey,
    pub pool: Pubkey,
    pub virtual_quote_reserves: i128,
    pub real_quote_reserves_after: u64,
}
