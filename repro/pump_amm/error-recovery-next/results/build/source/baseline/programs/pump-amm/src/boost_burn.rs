use crate::*;
use anchor_spl::token_interface::TokenInterface;
use anchor_spl::token_2022::spl_token_2022::{extension::{BaseStateWithExtensions, StateWithExtensions, transfer_fee::{TransferFeeConfig, instruction::harvest_withheld_tokens_to_mint}},state::Mint as SplMint};

#[event_cpi]
#[derive(Accounts)]
pub struct BoostBuyAndBurn<'info> {
    #[account(has_one=base_mint @ PumpAmmError::InvalidBaseMint,has_one=quote_mint @ PumpAmmError::InvalidQuoteMint,has_one=pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount,has_one=pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds=[b"global_config"],bump)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    #[account(mut)]
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)]
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    /// CHECK: Authority is bound to this pool by PDA seeds.
    #[account(seeds=[b"boost_vault",pool.key().as_ref()],bump)]
    pub boost_vault_authority: UncheckedAccount<'info>,
    #[account(mut,associated_token::mint=quote_mint,associated_token::authority=boost_vault_authority,associated_token::token_program=quote_token_program)]
    pub boost_vault: Box<InterfaceAccount<'info, TokenAccount>>,
    pub base_token_program: Interface<'info, TokenInterface>,
    pub quote_token_program: Interface<'info, TokenInterface>,
}

pub fn execute(ctx: Context<BoostBuyAndBurn>, requested: u64, minimum: u64) -> Result<()> {
    let a = &mut *ctx.accounts;
    require_keys_neq!(a.global_config.boost_authority, Pubkey::default(), PumpAmmError::InvalidAdmin);
    require_keys_eq!(a.global_config.boost_authority, a.authority.key(), PumpAmmError::InvalidAdmin);
    require!(a.global_config.boost_enabled, PumpAmmError::BoostDisabled);
    require!(a.global_config.disable_flags & 8 == 0, PumpAmmError::DisabledBuy);
    let effective = a.pool.protocol_fees.checked_add(a.pool.creator_fees)
        .and_then(|v| a.pool.virtual_quote_reserves.checked_add(v as i128));
    require!(effective.map_or(false, |v| v != 0), PumpAmmError::PoolCannotBoost);
    let old_vault = a.boost_vault.amount;
    let used = requested.min(old_vault);
    require!(used > 0, PumpAmmError::ZeroQuoteAmount);
    let has_fee = {
        let data = a.quote_mint.to_account_info();
        let data = data.try_borrow_data()?;
        let mint = StateWithExtensions::<SplMint>::unpack(&data)?;
        mint.get_extension::<TransferFeeConfig>().is_ok()
    };
    let transfer_fee = crate::quote_transfer_fee(&a.quote_mint.to_account_info(), used, false)?;
    let net = used.checked_sub(transfer_fee).ok_or(PumpAmmError::Overflow)?;
    require!(net > 0, PumpAmmError::ZeroQuoteAmount);
    let old_base = a.pool_base_token_account.amount;
    let old_quote = a.pool_quote_token_account.amount;
    let fees = a.pool.protocol_fees.checked_add(a.pool.creator_fees).ok_or(PumpAmmError::Overflow)?;
    old_quote.checked_sub(fees).ok_or(PumpAmmError::Overflow)?;
    let q = u64::try_from(a.pool.virtual_quote_reserves.checked_add(old_quote as i128).ok_or(PumpAmmError::Overflow)?).map_err(|_| error!(PumpAmmError::Overflow))?;
    let adjusted = net.checked_sub(1).ok_or(PumpAmmError::Overflow)? as u128;
    let denominator = (q as u128).checked_add(adjusted).ok_or(PumpAmmError::Overflow)?;
    let burned = u64::try_from((old_base as u128).checked_mul(adjusted).ok_or(PumpAmmError::Overflow)?.checked_div(denominator).ok_or(PumpAmmError::DivisionByZero)?).map_err(|_| error!(PumpAmmError::Truncation))?;
    require!(burned > 0, PumpAmmError::ZeroBaseAmount);
    require!(burned >= minimum, PumpAmmError::ExceededSlippage);
    require!(old_base > burned, PumpAmmError::TooLittlePoolTokenLiquidity);
    let pool_key = a.pool.key();
    let boost_bump = [ctx.bumps.boost_vault_authority];
    let boost_seeds: &[&[u8]] = &[b"boost_vault", pool_key.as_ref(), &boost_bump];
    token_interface::transfer_checked(CpiContext::new_with_signer(a.quote_token_program.to_account_info(), token_interface::TransferChecked {
        from: a.boost_vault.to_account_info(), mint: a.quote_mint.to_account_info(), to: a.pool_quote_token_account.to_account_info(), authority: a.boost_vault_authority.to_account_info(),
    }, &[boost_seeds]), used, a.quote_mint.decimals)?;
    let index = a.pool.index.to_le_bytes(); let bump = [a.pool.pool_bump];
    let seeds: &[&[u8]] = &[b"pool", &index, a.pool.creator.as_ref(), a.pool.base_mint.as_ref(), a.pool.quote_mint.as_ref(), &bump];
    token_interface::burn(CpiContext::new_with_signer(a.base_token_program.to_account_info(), token_interface::Burn {
        mint: a.base_mint.to_account_info(), from: a.pool_base_token_account.to_account_info(), authority: a.pool.to_account_info(),
    }, &[seeds]), burned)?;
    a.base_mint.reload()?;
    a.pool_base_token_account.reload()?;
    a.pool_quote_token_account.reload()?;
    a.boost_vault.reload()?;
    let timestamp = Clock::get()?.unix_timestamp;
    let event = crate::trade::BuyEvent {
        timestamp, base_amount_out: burned, max_quote_amount_in: requested,
        user_base_token_reserves: 0, user_quote_token_reserves: old_vault,
        pool_base_token_reserves: old_base, pool_quote_token_reserves: old_quote,
        quote_amount_in: net, lp_fee_basis_points: 0, lp_fee: 0,
        protocol_fee_basis_points: 0, protocol_fee: 0, quote_amount_in_with_lp_fee: net, user_quote_amount_in: net,
        pool: pool_key, user: a.boost_vault_authority.key(), user_base_token_account: Pubkey::default(), user_quote_token_account: a.boost_vault.key(),
        protocol_fee_recipient: Pubkey::default(), protocol_fee_recipient_token_account: Pubkey::default(), coin_creator: a.pool.coin_creator,
        coin_creator_fee_basis_points: 0, coin_creator_fee: 0, track_volume: false, total_unclaimed_tokens: 0, total_claimed_tokens: 0,
        current_sol_volume: 0, last_update_timestamp: 0, min_base_amount_out: minimum, ix_name: "buy_exact_quote_in".to_string(),
        cashback_fee_basis_points: 0, cashback: 0, buyback_fee_basis_points: 0, buyback_fee: 0,
        virtual_quote_reserves: a.pool.virtual_quote_reserves, can_boost: true,
        base_supply: if a.pool.is_mayhem_mode {1_000_000_000_000_000} else {a.base_mint.supply},
        holder_rewards_bps: 0, holder_rewards: 0, creator_fee_unclaimed: a.pool.creator_fees, quote_transfer_fee: transfer_fee,
    };
    emit!(event.clone()); emit_cpi!(event);
    let a = &mut *ctx.accounts;
    let event = BoostBuyAndBurnEvent {
        timestamp, mint: a.base_mint.key(), bonding_curve: Pubkey::find_program_address(&[b"bonding-curve", a.base_mint.key().as_ref()], &crate::trade::PUMP).0,
        pool: pool_key, authority: a.authority.key(), quote_amount_in_requested: requested, quote_amount_in_used: used,
        base_amount_burned: burned, virtual_quote_reserves: a.pool.virtual_quote_reserves,
        real_quote_reserves_after: a.pool_quote_token_account.amount, base_reserves_after: a.pool_base_token_account.amount, boost_vault_remaining: a.boost_vault.amount,
    };
    emit!(event.clone()); emit_cpi!(event);
    let a = &mut *ctx.accounts;
    if a.boost_vault.amount == 0 {
        if has_fee {
            require!(a.quote_mint.to_account_info().is_writable, PumpAmmError::QuoteMintNotWritable);
            let ix = harvest_withheld_tokens_to_mint(&a.quote_token_program.key(), &a.quote_mint.key(), &[&a.boost_vault.key()])?;
            anchor_lang::solana_program::program::invoke(&ix, &[a.quote_mint.to_account_info(), a.boost_vault.to_account_info(), a.quote_token_program.to_account_info()])?;
        }
        token_interface::close_account(CpiContext::new_with_signer(a.quote_token_program.to_account_info(), token_interface::CloseAccount {
            account: a.boost_vault.to_account_info(), destination: a.authority.to_account_info(), authority: a.boost_vault_authority.to_account_info(),
        }, &[boost_seeds]))?;
    }
    Ok(())
}

#[event]
#[derive(Clone)]
pub struct BoostBuyAndBurnEvent {
    pub timestamp: i64, pub mint: Pubkey, pub bonding_curve: Pubkey, pub pool: Pubkey, pub authority: Pubkey,
    pub quote_amount_in_requested: u64, pub quote_amount_in_used: u64, pub base_amount_burned: u64,
    pub virtual_quote_reserves: i128, pub real_quote_reserves_after: u64, pub base_reserves_after: u64, pub boost_vault_remaining: u64,
}
