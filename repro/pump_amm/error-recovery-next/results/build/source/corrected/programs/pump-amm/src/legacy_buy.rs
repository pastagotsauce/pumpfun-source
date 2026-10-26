use crate::*;
use anchor_lang::solana_program::{
    instruction::{AccountMeta, Instruction},
    program::{get_return_data, invoke},
};
use anchor_spl::{associated_token::AssociatedToken, token_interface::TokenInterface};
#[derive(Accounts)]
pub struct LegacyBuy<'info> {
    #[account(mut,has_one=base_mint @ PumpAmmError::InvalidBaseMint,has_one=quote_mint @ PumpAmmError::InvalidQuoteMint,has_one=pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount,has_one=pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    #[account(mut)]
    pub user: Signer<'info>,
    pub global_config: Box<Account<'info, GlobalConfig>>,
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)]
    pub user_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub user_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    /// CHECK: Authorization checked in handler.
    pub protocol_fee_recipient: UncheckedAccount<'info>,
    #[account(init_if_needed,payer=user,associated_token::mint=quote_mint,associated_token::authority=protocol_fee_recipient,associated_token::token_program=quote_token_program)]
    pub protocol_fee_recipient_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    pub base_token_program: Interface<'info, TokenInterface>,
    pub quote_token_program: Interface<'info, TokenInterface>,
    pub system_program: Program<'info, System>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    /// CHECK: Self event signer.
    #[account(seeds=[b"__event_authority"],bump)]
    pub event_authority: UncheckedAccount<'info>,
    pub program: Program<'info, trade::PumpAmmProgram>,
    #[account(init_if_needed,payer=user,associated_token::mint=quote_mint,associated_token::authority=coin_creator_vault_authority,associated_token::token_program=quote_token_program)]
    pub coin_creator_vault_ata: Box<InterfaceAccount<'info, TokenAccount>>,
    /// CHECK: Original PDA constraint.
    #[account(seeds=[b"creator_vault",pool.coin_creator.as_ref()],bump)]
    pub coin_creator_vault_authority: UncheckedAccount<'info>,
    #[account(seeds=[b"global_volume_accumulator"],bump)]
    pub global_volume_accumulator: Box<Account<'info, GlobalVolumeAccumulator>>,
    #[account(init_if_needed,payer=user,space=137,seeds=[b"user_volume_accumulator",user.key().as_ref()],bump)]
    pub user_volume_accumulator: Box<Account<'info, UserVolumeAccumulator>>,
    #[account(seeds=[b"fee_config",crate::ID.as_ref()],bump,seeds::program=fee_program.key())]
    pub fee_config: Box<Account<'info, trade::TradeFeeConfig>>,
    pub fee_program: Program<'info, LegacyBuyFeesProgram>,
}
pub struct LegacyBuyFeesProgram;
impl Id for LegacyBuyFeesProgram {
    fn id() -> Pubkey {
        trade::FEE_OWNER
    }
}
fn number(n: u128) -> Result<u64> {
    u64::try_from(n).map_err(|_| error!(PumpAmmError::Truncation))
}
fn fee(n: u64, bps: u64) -> Result<u64> {
    number(((n as u128) * (bps as u128) + 9999) / 10000)
}
fn transfer<'info>(
    program: &AccountInfo<'info>,
    mint: &InterfaceAccount<'info, Mint>,
    from: &AccountInfo<'info>,
    to: &AccountInfo<'info>,
    authority: &AccountInfo<'info>,
    amount: u64,
    seeds: &[&[&[u8]]],
) -> Result<()> {
    if amount == 0 {
        return Ok(());
    }
    if from.key == to.key {
        let source = TokenAccount::try_deserialize(&mut &from.try_borrow_data()?[..])?;
        require_keys_eq!(
            source.owner,
            authority.key(),
            PumpAmmError::SelfTransferNotAllowed
        );
    }
    token_interface::transfer_checked(
        CpiContext::new_with_signer(
            program.clone(),
            token_interface::TransferChecked {
                from: from.clone(),
                to: to.clone(),
                mint: mint.to_account_info(),
                authority: authority.clone(),
            },
            seeds,
        ),
        amount,
        mint.decimals,
    )
}
pub fn execute<'info>(
    ctx: Context<'_, '_, '_, 'info, LegacyBuy<'info>>,
    amount: u64,
    limit: u64,
    track: bool,
    exact: bool,
) -> Result<()> {
    let a = &mut *ctx.accounts;
    require!(
        a.global_config.disable_flags & 8 == 0,
        PumpAmmError::DisabledBuy
    );
    let pool_info = a.pool.to_account_info();
    if pool_info.data_len() < 287 {
        let rent = Rent::get()?
            .minimum_balance(287)
            .saturating_sub(pool_info.lamports());
        if rent > 0 {
            anchor_lang::system_program::transfer(
                CpiContext::new(
                    a.system_program.to_account_info(),
                    anchor_lang::system_program::Transfer {
                        from: a.user.to_account_info(),
                        to: pool_info.clone(),
                    },
                ),
                rent,
            )?;
        }
        pool_info.realloc(287, false)?;
    }
    let recipients = if a.pool.is_mayhem_mode {
        let mut r = [Pubkey::default(); 8];
        r[0] = a.global_config.reserved_fee_recipient;
        r[1..].copy_from_slice(&a.global_config.reserved_fee_recipients);
        r
    } else {
        a.global_config.protocol_fee_recipients
    };
    require!(
        recipients.contains(&a.protocol_fee_recipient.key()),
        PumpAmmError::InvalidProtocolFeeRecipient
    );
    require!(
        if exact { limit > 0 } else { amount > 0 },
        PumpAmmError::ZeroBaseAmount
    );
    require!(
        if exact { amount > 0 } else { limit > 0 },
        PumpAmmError::ZeroQuoteAmount
    );
    let available = if exact {
        let net = amount
            .checked_sub(crate::quote_transfer_fee(
                &a.quote_mint.to_account_info(),
                amount,
                false,
            )?)
            .ok_or(PumpAmmError::Overflow)?;
        require!(net > 0, PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees);
        net
    } else {
        amount
    };
    let old_virtual = a.pool.virtual_quote_reserves;
    let old_accrued = a
        .pool
        .protocol_fees
        .checked_add(a.pool.creator_fees)
        .ok_or(PumpAmmError::Overflow)?;
    let can_boost = old_virtual
        .checked_add(old_accrued as i128)
        .ok_or(PumpAmmError::Overflow)?
        != 0;
    a.pool_quote_token_account
        .amount
        .checked_sub(old_accrued)
        .ok_or(PumpAmmError::Overflow)?;
    let q = u64::try_from(
        (a.pool_quote_token_account.amount as i128)
            .checked_add(old_virtual)
            .ok_or(PumpAmmError::Overflow)?,
    )
    .map_err(|_| error!(PumpAmmError::Overflow))?;
    let b = a.pool_base_token_account.amount;
    let curve_initial = if exact {
        0
    } else {
        let denom = b
            .checked_sub(amount)
            .ok_or(PumpAmmError::BuyMoreBaseAmountThanPoolReserves)?;
        number(
            (q as u128)
                .checked_mul(amount as u128)
                .ok_or(PumpAmmError::Overflow)?
                .checked_div(denom as u128)
                .ok_or(PumpAmmError::DivisionByZero)?,
        )?
        .checked_add(1)
        .ok_or(PumpAmmError::Overflow)?
    };
    let canonical = a.pool.creator
        == Pubkey::find_program_address(
            &[b"pool-authority", a.base_mint.key().as_ref()],
            &trade::PUMP,
        )
        .0;
    let supply = if a.pool.is_mayhem_mode {
        1_000_000_000_000_000
    } else {
        a.base_mint.supply
    };
    let cap = (supply as u128)
        .checked_mul(q as u128)
        .ok_or(PumpAmmError::Overflow)?
        .checked_div(b as u128)
        .ok_or(PumpAmmError::DivisionByZero)?;
    let mut data = vec![154, 237, 138, 92, 162, 2, 162, 187, canonical as u8];
    data.extend_from_slice(&cap.to_le_bytes());
    data.extend_from_slice(a.quote_mint.key().as_ref());
    invoke(
        &Instruction {
            program_id: trade::FEE_OWNER,
            accounts: vec![
                AccountMeta::new_readonly(a.fee_config.key(), false),
                AccountMeta::new_readonly(crate::ID, false),
            ],
            data,
        },
        &[
            a.fee_config.to_account_info(),
            a.program.to_account_info(),
            a.fee_program.to_account_info(),
        ],
    )?;
    let (_, returned) = get_return_data().ok_or(PumpAmmError::AccountTypeNotSupported)?;
    let mut selected = trade::TradeFees::deserialize(&mut &returned[..])?;
    if a.pool.creator_fee_bps != 0 {
        selected.creator_fee_bps = a.pool.creator_fee_bps;
    }
    let creator_bps = if a.pool.coin_creator == Pubkey::default() {
        0
    } else {
        selected.creator_fee_bps
    };
    let (base_out, curve, lp_fee, protocol_fee, creator_fee, total) = if exact {
        let sum = number(
            selected.lp_fee_bps as u128
                + selected.protocol_fee_bps as u128
                + creator_bps as u128
                + 10000,
        )?;
        let estimate = number((available as u128) * 10000 / (sum as u128))?;
        require!(
            estimate > 0,
            PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees
        );
        let l = fee(estimate, selected.lp_fee_bps)?;
        let p = fee(estimate, selected.protocol_fee_bps)?;
        let c = fee(estimate, creator_bps)?;
        estimate
            .checked_add(l)
            .and_then(|n| n.checked_add(p))
            .and_then(|n| n.checked_add(c))
            .ok_or(PumpAmmError::Overflow)?;
        let curve = available
            .checked_sub(l)
            .and_then(|n| n.checked_sub(p))
            .and_then(|n| n.checked_sub(c))
            .ok_or(PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees)?
            .min(estimate);
        let adjusted = curve.saturating_sub(1);
        let out = number((b as u128) * (adjusted as u128) / ((q as u128) + (adjusted as u128)))?;
        require!(out >= limit, PumpAmmError::BuySlippageBelowMinBaseAmountOut);
        (
            out,
            curve,
            l,
            p,
            c,
            curve
                .checked_add(l)
                .and_then(|n| n.checked_add(p))
                .and_then(|n| n.checked_add(c))
                .ok_or(PumpAmmError::Overflow)?,
        )
    } else {
        let l = fee(curve_initial, selected.lp_fee_bps)?;
        let p = fee(curve_initial, selected.protocol_fee_bps)?;
        let c = fee(curve_initial, creator_bps)?;
        let total = curve_initial
            .checked_add(l)
            .and_then(|n| n.checked_add(p))
            .and_then(|n| n.checked_add(c))
            .ok_or(PumpAmmError::Overflow)?;
        (amount, curve_initial, l, p, c, total)
    };
    let pool_quote = curve.checked_add(lp_fee).ok_or(PumpAmmError::Overflow)?;
    let quote_transfer_fee =
        crate::quote_transfer_fee(&a.quote_mint.to_account_info(), pool_quote, true)?;
    if !exact {
        require!(
            total
                .checked_add(quote_transfer_fee)
                .ok_or(PumpAmmError::Overflow)?
                <= limit,
            PumpAmmError::ExceededSlippage
        );
    }
    let index = a.pool.index.to_le_bytes();
    let bump = [a.pool.pool_bump];
    let creator = a.pool.creator;
    let base = a.pool.base_mint;
    let quote = a.pool.quote_mint;
    let seeds: &[&[u8]] = &[
        b"pool",
        &index,
        creator.as_ref(),
        base.as_ref(),
        quote.as_ref(),
        &bump,
    ];
    transfer(
        &a.base_token_program.to_account_info(),
        &a.base_mint,
        &a.pool_base_token_account.to_account_info(),
        &a.user_base_token_account.to_account_info(),
        &pool_info,
        base_out,
        &[seeds],
    )?;
    transfer_quote(a, &a.pool_quote_token_account.to_account_info(), pool_quote)?;
    let buyback_bps = if a.pool.is_mayhem_mode {
        0
    } else {
        a.global_config.buyback_basis_points
    };
    let buyback_fee = u64::try_from((protocol_fee as u128) * (buyback_bps as u128) / 10000)
        .expect("buyback fee is at most protocol_fee");
    let net_protocol = protocol_fee
        .checked_sub(buyback_fee)
        .expect("buyback_fee never exceeds protocol_fee");
    transfer_fee(
        a,
        &a.protocol_fee_recipient_token_account.to_account_info(),
        net_protocol,
    )?;
    let mut next = 0;
    if creator_fee > 0 {
        if a.pool.is_cashback_coin && creator_fee > 0 {
            let dest = ctx
                .remaining_accounts
                .get(0)
                .ok_or(PumpAmmError::MissingCashbackAccounts)?;
            let expected =
                anchor_spl::associated_token::get_associated_token_address_with_program_id(
                    &a.user_volume_accumulator.key(),
                    &a.quote_mint.key(),
                    &a.quote_token_program.key(),
                );
            require_keys_eq!(
                dest.key(),
                expected,
                PumpAmmError::InvalidCashbackAccumulatorAta
            );
            require!(
                dest.is_writable,
                PumpAmmError::InvalidCashbackAccumulatorAta
            );
            if dest.data_is_empty() {
                create_ata(a, dest, &a.user_volume_accumulator.to_account_info(), false)?;
            }
            transfer_fee(a, dest, creator_fee)?;
            a.user_volume_accumulator.cashback_earned = a
                .user_volume_accumulator
                .cashback_earned
                .checked_add(creator_fee)
                .ok_or(PumpAmmError::Overflow)?;
            next = 1;
        }
        let extra = ctx
            .remaining_accounts
            .get(next)
            .ok_or(PumpAmmError::InvalidPoolV2)?;
        require_keys_eq!(
            extra.key(),
            Pubkey::find_program_address(&[b"pool-v2", a.base_mint.key().as_ref()], &crate::ID).0,
            PumpAmmError::InvalidPoolV2
        );
        next += 1;
        if !a.pool.is_cashback_coin {
            transfer_fee(a, &a.coin_creator_vault_ata.to_account_info(), creator_fee)?;
        }
    }
    let owner = ctx
        .remaining_accounts
        .get(next)
        .ok_or(PumpAmmError::BuybackFeeRecipientMissing)?;
    let dest = ctx
        .remaining_accounts
        .get(next + 1)
        .ok_or(PumpAmmError::BuybackFeeRecipientMissing)?;
    require!(
        a.global_config.buyback_fee_recipients.contains(owner.key),
        PumpAmmError::BuybackFeeRecipientNotAuthorized
    );
    let expected = anchor_spl::associated_token::get_associated_token_address_with_program_id(
        owner.key,
        &a.quote_mint.key(),
        &a.quote_token_program.key(),
    );
    require_keys_eq!(
        dest.key(),
        expected,
        PumpAmmError::BuybackFeeRecipientNotAuthorized
    );
    if buyback_fee > 0 {
        if dest.data_is_empty() {
            create_ata(a, dest, owner, true)?;
        }
        transfer_fee(a, dest, buyback_fee)?;
    }
    a.user_volume_accumulator.user = a.user.key();
    let event = trade::BuyEvent {
        timestamp: Clock::get()?.unix_timestamp,
        base_amount_out: base_out,
        max_quote_amount_in: if exact { amount } else { limit },
        user_base_token_reserves: a.user_base_token_account.amount,
        user_quote_token_reserves: a.user_quote_token_account.amount,
        pool_base_token_reserves: a.pool_base_token_account.amount,
        pool_quote_token_reserves: a.pool_quote_token_account.amount,
        quote_amount_in: if exact { amount } else { curve },
        lp_fee_basis_points: selected.lp_fee_bps,
        lp_fee,
        protocol_fee_basis_points: selected.protocol_fee_bps,
        protocol_fee,
        quote_amount_in_with_lp_fee: pool_quote,
        user_quote_amount_in: if exact { curve } else { total },
        pool: a.pool.key(),
        user: a.user.key(),
        user_base_token_account: a.user_base_token_account.key(),
        user_quote_token_account: a.user_quote_token_account.key(),
        protocol_fee_recipient: a.protocol_fee_recipient.key(),
        protocol_fee_recipient_token_account: a.protocol_fee_recipient_token_account.key(),
        coin_creator: a.pool.coin_creator,
        coin_creator_fee_basis_points: if a.pool.is_cashback_coin && creator_fee > 0 {
            0
        } else {
            selected.creator_fee_bps
        },
        coin_creator_fee: if a.pool.is_cashback_coin && creator_fee > 0 {
            0
        } else {
            creator_fee
        },
        track_volume: track,
        total_unclaimed_tokens: a.user_volume_accumulator.total_unclaimed_tokens,
        total_claimed_tokens: a.user_volume_accumulator.total_claimed_tokens,
        current_sol_volume: a.user_volume_accumulator.current_sol_volume,
        last_update_timestamp: a.user_volume_accumulator.last_update_timestamp,
        min_base_amount_out: if exact { limit } else { amount },
        ix_name: if exact {
            "buy_exact_quote_in".to_string()
        } else {
            "buy".to_string()
        },
        cashback_fee_basis_points: if a.pool.is_cashback_coin && creator_fee > 0 {
            selected.creator_fee_bps
        } else {
            0
        },
        cashback: if a.pool.is_cashback_coin && creator_fee > 0 {
            creator_fee
        } else {
            0
        },
        buyback_fee_basis_points: buyback_bps,
        buyback_fee: buyback_fee
            .checked_sub(crate::quote_transfer_fee(
                &a.quote_mint.to_account_info(),
                buyback_fee,
                false,
            )?)
            .ok_or(PumpAmmError::Overflow)?,
        virtual_quote_reserves: old_virtual,
        can_boost,
        base_supply: supply,
        holder_rewards_bps: if a.pool.is_holder_reward {
            selected.creator_fee_bps
        } else {
            0
        },
        holder_rewards: if a.pool.is_holder_reward {
            creator_fee
        } else {
            0
        },
        creator_fee_unclaimed: a.pool.creator_fees,
        quote_transfer_fee,
    };
    emit!(event.clone());
    emit_cpi!(event);
    Ok(())
}
fn transfer_quote<'info>(
    a: &LegacyBuy<'info>,
    dest: &AccountInfo<'info>,
    amount: u64,
) -> Result<()> {
    let extra = crate::quote_transfer_fee(&a.quote_mint.to_account_info(), amount, true)?;
    let gross = amount.checked_add(extra).ok_or(PumpAmmError::Overflow)?;
    transfer(
        &a.quote_token_program.to_account_info(),
        &a.quote_mint,
        &a.user_quote_token_account.to_account_info(),
        dest,
        &a.user.to_account_info(),
        gross,
        &[],
    )
}
fn create_ata<'info>(
    a: &LegacyBuy<'info>,
    ata: &AccountInfo<'info>,
    owner: &AccountInfo<'info>,
    idempotent: bool,
) -> Result<()> {
    let create = if idempotent {
        anchor_spl::associated_token::create_idempotent
    } else {
        anchor_spl::associated_token::create
    };
    create(CpiContext::new(
        a.associated_token_program.to_account_info(),
        anchor_spl::associated_token::Create {
            payer: a.user.to_account_info(),
            associated_token: ata.clone(),
            authority: owner.clone(),
            mint: a.quote_mint.to_account_info(),
            system_program: a.system_program.to_account_info(),
            token_program: a.quote_token_program.to_account_info(),
        },
    ))
}

fn transfer_fee<'info>(a: &LegacyBuy<'info>, dest: &AccountInfo<'info>, amount: u64) -> Result<()> {
    transfer(
        &a.quote_token_program.to_account_info(),
        &a.quote_mint,
        &a.user_quote_token_account.to_account_info(),
        dest,
        &a.user.to_account_info(),
        amount,
        &[],
    )
}
