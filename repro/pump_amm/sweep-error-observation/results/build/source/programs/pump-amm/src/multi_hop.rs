//! Partial reconstruction from captured AMM execution and static control flow.
//! Ordinary signed offline fixtures cover AMM legs and genuine captured Pump CPIs;
//! this is not the historical source or a claim of whole-program equivalence.
use super::*;
use anchor_lang::solana_program::{
    instruction::{AccountMeta, Instruction},
    program::{get_return_data, invoke_signed},
};
use std::collections::BTreeSet;
#[derive(Accounts)]
pub struct MultiHop<'info> {
    #[account(mut)]
    pub user: Signer<'info>,
    #[account(mut)]
    pub user_in_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub user_out_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(seeds=[b"global_config"],bump)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    #[account(seeds=[b"fee_config",crate::ID.as_ref()],bump,seeds::program=FEE_OWNER)]
    pub fee_config: Box<Account<'info, TradeFeeConfig>>,
    #[account(init_if_needed,payer=user,space=137,seeds=[b"user_volume_accumulator",user.key().as_ref()],bump)]
    pub user_volume_accumulator: Box<Account<'info, UserVolumeAccumulator>>,
    /// CHECK: Validated at a protocol-fee endpoint or by the captured Pump CPI.
    #[account(mut)]
    pub buyback_fee_recipient: UncheckedAccount<'info>,
    pub token_program: Program<'info, Token>,
    pub token_2022_program: Program<'info, Token2022>,
    pub system_program: Program<'info, System>,
    /// CHECK: Self-event PDA.
    #[account(seeds=[b"__event_authority"],bump)]
    pub event_authority: UncheckedAccount<'info>,
    pub program: Program<'info, PumpAmmProgram>,
    pub pump_program: Program<'info, PumpProgram>,
    /// CHECK: Forwarded unchanged to Pump, which validates its context.
    pub pump_global: UncheckedAccount<'info>,
    /// CHECK: Forwarded unchanged to Pump, which validates its context.
    pub pump_fee_config: UncheckedAccount<'info>,
    /// CHECK: Forwarded unchanged to Pump, which validates its context.
    pub pump_event_authority: UncheckedAccount<'info>,
}
pub struct PumpProgram;
impl Id for PumpProgram {
    fn id() -> Pubkey {
        PUMP
    }
}
#[derive(Accounts)]
pub struct AmmHop<'info> {
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut,has_one=base_mint @ PumpAmmError::InvalidBaseMint,has_one=quote_mint @ PumpAmmError::InvalidQuoteMint,has_one=pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount,has_one=pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    #[account(mut)]
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
}
fn checked64(n: u128) -> Result<u64> {
    u64::try_from(n).map_err(|_| error!(PumpAmmError::Truncation))
}
fn fee(n: u64, bps: u64) -> Result<u64> {
    checked64(((n as u128) * (bps as u128) + 9999) / 10000)
}
fn token_amount(a: &AccountInfo) -> Result<u64> {
    Ok(TokenAccount::try_deserialize(&mut &a.try_borrow_data()?[..])?.amount)
}
fn program_for<'info>(
    a: &MultiHop<'info>,
    mint: &AccountInfo<'info>,
) -> Result<AccountInfo<'info>> {
    if *mint.owner == anchor_spl::token::ID {
        Ok(a.token_program.to_account_info())
    } else if *mint.owner == anchor_spl::token_2022::ID {
        Ok(a.token_2022_program.to_account_info())
    } else {
        err!(PumpAmmError::AccountTypeNotSupported)
    }
}
fn pool_seed_parts(pool: &Pool) -> Vec<Vec<u8>> {
    vec![
        b"pool".to_vec(),
        pool.index.to_le_bytes().to_vec(),
        pool.creator.to_bytes().to_vec(),
        pool.base_mint.to_bytes().to_vec(),
        pool.quote_mint.to_bytes().to_vec(),
        vec![pool.pool_bump],
    ]
}
fn transfer<'info>(
    program: AccountInfo<'info>,
    mint: AccountInfo<'info>,
    from: AccountInfo<'info>,
    to: AccountInfo<'info>,
    authority: AccountInfo<'info>,
    amount: u64,
    decimals: u8,
    seeds: &[Vec<u8>],
) -> Result<()> {
    if amount == 0 {
        return Ok(());
    }
    if from.key() == to.key() {
        let state = TokenAccount::try_deserialize(&mut &from.try_borrow_data()?[..])?;
        require_keys_eq!(
            state.owner,
            authority.key(),
            PumpAmmError::SelfTransferNotAllowed
        );
    }
    let refs: Vec<&[u8]> = seeds.iter().map(|s| s.as_slice()).collect();
    let signers = [refs.as_slice()];
    token_interface::transfer_checked(
        CpiContext::new_with_signer(
            program,
            token_interface::TransferChecked {
                from,
                to,
                mint,
                authority,
            },
            if seeds.is_empty() { &[] } else { &signers },
        ),
        amount,
        decimals,
    )
}
fn emit_event<'info, T: anchor_lang::Event + Clone>(a: &MultiHop<'info>, event: T) -> Result<()> {
    anchor_lang::solana_program::log::sol_log_data(&[&event.data()]);
    let data = [
        vec![0xe4, 0x45, 0xa5, 0x2e, 0x51, 0xcb, 0x9a, 0x1d],
        event.data(),
    ]
    .concat();
    let bump = Pubkey::find_program_address(&[b"__event_authority"], &crate::ID).1;
    invoke_signed(
        &Instruction {
            program_id: crate::ID,
            accounts: vec![AccountMeta::new_readonly(a.event_authority.key(), true)],
            data,
        },
        &[
            a.event_authority.to_account_info(),
            a.program.to_account_info(),
        ],
        &[&[b"__event_authority", &[bump]]],
    )?;
    Ok(())
}
fn fees(a: &MultiHop, h: &AmmHop, quote_reserve: u64, base_reserve: u64) -> Result<TradeFees> {
    require!(
        a.fee_config.to_account_info().data_len() >= 2512,
        PumpAmmError::FeeConfigTooShort
    );
    let authority =
        Pubkey::find_program_address(&[b"pool-authority", h.base_mint.key().as_ref()], &PUMP).0;
    let mut selected = if h.pool.creator != authority {
        a.fee_config.flat_fees.clone()
    } else {
        let cap = (if h.pool.is_mayhem_mode {
            1_000_000_000_000_000u64
        } else {
            h.base_mint.supply
        } as u128)
            .checked_mul(quote_reserve as u128)
            .ok_or(PumpAmmError::Overflow)?
            .checked_div(base_reserve as u128)
            .ok_or(PumpAmmError::DivisionByZero)?;
        let config = &a.fee_config;
        let quote = h.quote_mint.key();
        let other_normal = Pubkey::new_from_array([
            131, 13, 252, 159, 222, 95, 230, 184, 170, 124, 4, 164, 118, 233, 30, 138, 198, 187,
            38, 74, 173, 144, 250, 25, 201, 223, 73, 216, 92, 62, 91, 94,
        ]);
        if quote != Pubkey::default()
            && quote != anchor_spl::token::spl_token::native_mint::ID
            && quote != other_normal
            && quote
                != anchor_lang::solana_program::pubkey!(
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                )
        {
            if config.exotic_flat_fees.lp_fee_bps == 0
                && config.exotic_flat_fees.protocol_fee_bps == 0
                && config.exotic_flat_fees.creator_fee_bps == 0
            {
                config.flat_fees.clone()
            } else {
                config.exotic_flat_fees.clone()
            }
        } else {
            let tiers = if quote
                == anchor_lang::solana_program::pubkey!(
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                ) {
                &config.stable_fee_tiers
            } else {
                &config.fee_tiers
            };
            require!(!tiers.is_empty(), PumpAmmError::FeeTiersEmpty);
            if cap < tiers[0].market_cap_lamports_threshold {
                tiers[0].fees.clone()
            } else {
                tiers
                    .iter()
                    .rev()
                    .find(|t| cap >= t.market_cap_lamports_threshold)
                    .unwrap_or(&tiers[0])
                    .fees
                    .clone()
            }
        }
    };
    if h.pool.creator_fee_bps != 0 {
        selected.creator_fee_bps = h.pool.creator_fee_bps;
    }
    Ok(selected)
}
pub fn execute<'info>(
    ctx: Context<'_, '_, 'info, 'info, MultiHop<'info>>,
    amount: u64,
    minimum: u64,
) -> Result<()> {
    let a = &mut *ctx.accounts;
    require!(amount > 0, PumpAmmError::ZeroQuoteAmount);
    require!(minimum > 0, PumpAmmError::ZeroBaseAmount);
    let remaining = ctx.remaining_accounts;
    require!(
        !remaining.is_empty() && remaining.len() % 5 == 0,
        PumpAmmError::NotEnoughRemainingAccounts
    );
    let count = remaining.len() / 5;
    let mut current_mint = a.user_in_token_account.mint;
    let mut sell = None;
    for group in remaining.chunks(5) {
        let next_sell = if current_mint == group[1].key() {
            current_mint = group[0].key();
            false
        } else if current_mint == group[0].key() {
            current_mint = group[1].key();
            true
        } else {
            return err!(PumpAmmError::MultiHopDiscontinuousPath);
        };
        if let Some(old) = sell {
            require!(old == next_sell, PumpAmmError::MultiHopMixedDirection);
        } else {
            sell = Some(next_sell);
        }
    }
    require_keys_eq!(
        current_mint,
        a.user_out_token_account.mint,
        PumpAmmError::MultiHopDiscontinuousPath
    );
    let sell = sell.unwrap();
    let mut i = 0;
    let mut current = amount;
    let mut source = a.user_in_token_account.to_account_info();
    let mut authority = a.user.to_account_info();
    let mut source_seeds: Vec<Vec<u8>> = vec![];
    let mut prepaid = false;
    while i < count {
        let group = &remaining[i * 5..(i + 1) * 5];
        if *group[2].owner == PUMP {
            let start = i;
            i += 1;
            while i < count && *remaining[i * 5 + 2].owner == PUMP {
                i += 1;
            }
            let destination = if i == count {
                a.user_out_token_account.to_account_info()
            } else {
                remaining[i * 5 + if sell { 3 } else { 4 }].clone()
            };
            let before = token_amount(&destination)?;
            let source_before = token_amount(&source)?;
            let input_native = !sell
                && remaining[start * 5 + 1].key() == anchor_spl::token::spl_token::native_mint::ID;
            let output_native = sell
                && remaining[(i - 1) * 5 + 1].key()
                    == anchor_spl::token::spl_token::native_mint::ID;
            let mut infos = vec![
                a.pump_global.to_account_info(),
                a.pump_fee_config.to_account_info(),
                a.global_config.to_account_info(),
                a.user.to_account_info(),
                authority.clone(),
                source.clone(),
                destination.clone(),
                a.buyback_fee_recipient.to_account_info(),
                a.token_program.to_account_info(),
                a.token_2022_program.to_account_info(),
                a.system_program.to_account_info(),
                a.pump_event_authority.to_account_info(),
                a.pump_program.to_account_info(),
            ];
            let flags: Vec<u8> = (start..i)
                .map(|j| {
                    let protocol = if sell { j + 1 == count } else { j == 0 };
                    let creator = if sell { j == 0 } else { j + 1 == count };
                    (protocol as u8) | ((creator as u8) << 1)
                })
                .collect();
            let mut data = vec![225, 154, 117, 22, 215, 86, 246, 103];
            data.extend(amount_bytes(current));
            data.extend((flags.len() as u32).to_le_bytes());
            data.extend(flags);
            let mut metas = vec![
                AccountMeta::new_readonly(a.pump_global.key(), false),
                AccountMeta::new_readonly(a.pump_fee_config.key(), false),
                AccountMeta::new_readonly(a.global_config.key(), true),
                AccountMeta::new(a.user.key(), true),
                AccountMeta::new_readonly(authority.key(), true),
                AccountMeta::new(source.key(), false),
                AccountMeta::new(destination.key(), false),
                AccountMeta::new(a.buyback_fee_recipient.key(), false),
                AccountMeta::new_readonly(a.token_program.key(), false),
                AccountMeta::new_readonly(a.token_2022_program.key(), false),
                AccountMeta::new_readonly(a.system_program.key(), false),
                AccountMeta::new_readonly(a.pump_event_authority.key(), false),
                AccountMeta::new_readonly(a.pump_program.key(), false),
            ];
            for info in &remaining[start * 5..i * 5] {
                metas.push(if info.is_writable {
                    AccountMeta::new(info.key(), info.is_signer)
                } else {
                    AccountMeta::new_readonly(info.key(), info.is_signer)
                });
                infos.push(info.clone());
            }
            let bump = [ctx.bumps.global_config];
            let config_seeds: &[&[u8]] = &[b"global_config", &bump];
            let refs: Vec<&[u8]> = source_seeds.iter().map(|v| v.as_slice()).collect();
            let mut signers = vec![config_seeds];
            if !refs.is_empty() {
                signers.push(refs.as_slice());
            }
            invoke_signed(
                &Instruction {
                    program_id: PUMP,
                    accounts: metas,
                    data,
                },
                &infos,
                &signers,
            )?;
            let (program, ret) = get_return_data().ok_or(PumpAmmError::MultiHopCurveRunMismatch)?;
            require!(
                program == PUMP && ret.len() == 16,
                PumpAmmError::MultiHopCurveRunMismatch
            );
            let output = u64::from_le_bytes(ret[..8].try_into().unwrap());
            let buyback = u64::from_le_bytes(ret[8..16].try_into().unwrap());
            if !input_native {
                let expected = source_before
                    .checked_sub(current)
                    .and_then(|v| {
                        v.checked_add(if source.key() == destination.key() {
                            output
                        } else {
                            0
                        })
                    })
                    .and_then(|v| {
                        v.checked_add(if source.key() == a.buyback_fee_recipient.key() {
                            buyback
                        } else {
                            0
                        })
                    })
                    .ok_or(PumpAmmError::Overflow)?;
                require!(
                    token_amount(&source)? == expected,
                    PumpAmmError::MultiHopCurveRunMismatch
                );
            }
            if !output_native && source.key() != destination.key() {
                let expected = before
                    .checked_add(output)
                    .and_then(|v| {
                        v.checked_add(if destination.key() == a.buyback_fee_recipient.key() {
                            buyback
                        } else {
                            0
                        })
                    })
                    .ok_or(PumpAmmError::Overflow)?;
                require!(
                    token_amount(&destination)? == expected,
                    PumpAmmError::MultiHopCurveRunMismatch
                );
            }
            current = output;
            source = destination;
            prepaid = true;
            source_seeds.clear();
        } else {
            require_keys_eq!(
                *group[2].owner,
                crate::ID,
                PumpAmmError::AccountTypeNotSupported
            );
            let mut slice = group;
            let mut bumps = AmmHopBumps {};
            let mut reallocs = BTreeSet::new();
            let mut hop =
                AmmHop::try_accounts(&crate::ID, &mut slice, &[], &mut bumps, &mut reallocs)?;
            current = amm_hop(
                a,
                &mut hop,
                current,
                if i + 1 == count { minimum } else { 0 },
                sell,
                i == 0,
                i + 1 == count,
                prepaid,
                &source,
                &authority,
                &source_seeds,
            )?;
            hop.exit(&crate::ID)?;
            source = if sell {
                hop.pool_quote_token_account.to_account_info()
            } else {
                hop.pool_base_token_account.to_account_info()
            };
            authority = hop.pool.to_account_info();
            source_seeds = pool_seed_parts(&hop.pool);
            prepaid = false;
            i += 1;
        }
    }
    require!(current >= minimum, PumpAmmError::ExceededSlippage);
    if a.user_volume_accumulator.user == Pubkey::default() {
        a.user_volume_accumulator.user = a.user.key();
    }
    Ok(())
}
fn amount_bytes(n: u64) -> [u8; 8] {
    n.to_le_bytes()
}

#[inline(never)]
fn amm_hop<'info>(
    a: &MultiHop<'info>,
    h: &mut AmmHop<'info>,
    amount: u64,
    minimum: u64,
    sell: bool,
    first: bool,
    last: bool,
    prepaid: bool,
    source: &AccountInfo<'info>,
    source_authority: &AccountInfo<'info>,
    source_seeds: &[Vec<u8>],
) -> Result<u64> {
    require!(
        a.global_config.disable_flags & (if sell { 16 } else { 8 }) == 0,
        if sell {
            PumpAmmError::DisabledSell
        } else {
            PumpAmmError::DisabledBuy
        }
    );
    let canonical =
        Pubkey::find_program_address(&[b"pool-authority", h.base_mint.key().as_ref()], &PUMP).0;
    require_keys_eq!(h.pool.creator, canonical, PumpAmmError::OnlyPumpPools);
    require!(
        !h.pool.is_cashback_coin,
        PumpAmmError::CashbackCoinNotSupported
    );
    require!(!h.pool.is_mayhem_mode, PumpAmmError::MayhemPoolNotSupported);
    let pool_info = h.pool.to_account_info();
    if pool_info.data_len() < 287 {
        let top = Rent::get()?
            .minimum_balance(287)
            .saturating_sub(pool_info.lamports());
        if top > 0 {
            anchor_lang::system_program::transfer(
                CpiContext::new(
                    a.system_program.to_account_info(),
                    anchor_lang::system_program::Transfer {
                        from: a.user.to_account_info(),
                        to: pool_info.clone(),
                    },
                ),
                top,
            )?;
        }
        pool_info.realloc(287, false)?;
    }
    let base_program = program_for(a, &h.base_mint.to_account_info())?;
    let quote_program = program_for(a, &h.quote_mint.to_account_info())?;
    let protocol_end = if sell { last } else { first };
    let creator_end = if sell { first } else { last };
    if protocol_end {
        require_keys_eq!(
            *a.buyback_fee_recipient.to_account_info().owner,
            quote_program.key(),
            PumpAmmError::AccountTypeNotSupported
        );
        let buyback_info = a.buyback_fee_recipient.to_account_info();
        let state = TokenAccount::try_deserialize(&mut &buyback_info.try_borrow_data()?[..])?;
        require_keys_eq!(
            state.mint,
            h.quote_mint.key(),
            PumpAmmError::InvalidQuoteMint
        );
        require!(
            a.global_config
                .buyback_fee_recipients
                .contains(&state.owner),
            PumpAmmError::BuybackFeeRecipientNotAuthorized
        );
        let expected = Pubkey::find_program_address(
            &[
                state.owner.as_ref(),
                quote_program.key.as_ref(),
                h.quote_mint.key().as_ref(),
            ],
            &anchor_spl::associated_token::ID,
        )
        .0;
        require_keys_eq!(
            expected,
            a.buyback_fee_recipient.key(),
            PumpAmmError::BuybackFeeRecipientNotAuthorized
        );
    }
    let user_input_balance = if first {
        a.user_in_token_account.amount
    } else {
        0
    };
    let user_output_balance = if last {
        token_amount(&a.user_out_token_account.to_account_info())?
    } else {
        0
    };
    let input_mint = if sell {
        h.base_mint.to_account_info()
    } else {
        h.quote_mint.to_account_info()
    };
    let input_program = if sell {
        base_program.clone()
    } else {
        quote_program.clone()
    };
    let input_decimals = if sell {
        h.base_mint.decimals
    } else {
        h.quote_mint.decimals
    };
    let input_vault = if sell {
        h.pool_base_token_account.to_account_info()
    } else {
        h.pool_quote_token_account.to_account_info()
    };
    if !prepaid && (first || source.key() != input_vault.key()) {
        transfer(
            input_program,
            input_mint,
            source.clone(),
            input_vault,
            source_authority.clone(),
            amount,
            input_decimals,
            source_seeds,
        )?;
    }
    h.pool_base_token_account.reload()?;
    h.pool_quote_token_account.reload()?;
    let input_tf = if sell {
        0
    } else {
        quote_transfer_fee(&h.quote_mint.to_account_info(), amount, false)?
    };
    let received = amount.checked_sub(input_tf).ok_or(PumpAmmError::Overflow)?;
    let b = if sell {
        h.pool_base_token_account
            .amount
            .checked_sub(amount)
            .ok_or(PumpAmmError::Overflow)?
    } else {
        h.pool_base_token_account.amount
    };
    let raw_q = if sell {
        h.pool_quote_token_account.amount
    } else {
        h.pool_quote_token_account
            .amount
            .checked_sub(received)
            .ok_or(PumpAmmError::Overflow)?
    };
    let old_virtual = h.pool.virtual_quote_reserves;
    let old_accrued = h
        .pool
        .protocol_fees
        .checked_add(h.pool.creator_fees)
        .ok_or(PumpAmmError::Overflow)?;
    raw_q
        .checked_sub(old_accrued)
        .ok_or(PumpAmmError::Overflow)?;
    let q = u64::try_from(
        (raw_q as i128)
            .checked_add(old_virtual)
            .ok_or(PumpAmmError::Overflow)?,
    )
    .map_err(|_| error!(PumpAmmError::Overflow))?;
    let can_boost = old_virtual
        .checked_add(old_accrued as i128)
        .ok_or(PumpAmmError::Overflow)?
        != 0;
    // Fee selection uses the reserves before the already-completed input transfer.
    let mut selected = fees(a, h, q, b)?;
    if !creator_end {
        selected.lp_fee_bps = 0;
        selected.creator_fee_bps = 0;
    }
    if !protocol_end {
        selected.protocol_fee_bps = 0;
    }
    let creator_bps = if h.pool.coin_creator == Pubkey::default() {
        0
    } else {
        selected.creator_fee_bps
    };
    let (base_amount, curve_quote, lp_fee, protocol_fee, creator_fee, total_quote) = if sell {
        let curve = checked64((q as u128) * (amount as u128) / ((b as u128) + (amount as u128)))?;
        let l = fee(curve, selected.lp_fee_bps)?;
        let p = fee(curve, selected.protocol_fee_bps)?;
        let c = fee(curve, creator_bps)?;
        let total = curve
            .checked_sub(l)
            .and_then(|v| v.checked_sub(p))
            .and_then(|v| v.checked_sub(c))
            .ok_or(PumpAmmError::Overflow)?;
        require!(total > 0, PumpAmmError::ZeroQuoteAmount);
        (amount, curve, l, p, c, total)
    } else {
        let sum = checked64(
            10000
                + selected.lp_fee_bps as u128
                + selected.protocol_fee_bps as u128
                + creator_bps as u128,
        )?;
        let estimate = checked64((received as u128) * 10000 / (sum as u128))?;
        require!(
            estimate > 0,
            PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees
        );
        let l = fee(estimate, selected.lp_fee_bps)?;
        let p = fee(estimate, selected.protocol_fee_bps)?;
        let c = fee(estimate, creator_bps)?;
        let total = estimate
            .checked_add(l)
            .and_then(|v| v.checked_add(p))
            .and_then(|v| v.checked_add(c))
            .ok_or(PumpAmmError::Overflow)?;
        let excess = total.saturating_sub(received);
        let adjusted_estimate = estimate
            .checked_sub(excess)
            .ok_or(PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees)?;
        require!(
            adjusted_estimate > 0,
            PumpAmmError::BuySlippageBelowMinBaseAmountOut
        );
        let curve = received
            .checked_sub(l)
            .and_then(|v| v.checked_sub(p))
            .and_then(|v| v.checked_sub(c))
            .ok_or(PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees)?;
        let adjusted = curve.saturating_sub(1);
        let out = checked64((b as u128) * (adjusted as u128) / ((q as u128) + (adjusted as u128)))?;
        require!(out > 0, PumpAmmError::ZeroBaseAmount);
        require!(out < b, PumpAmmError::BuyMoreBaseAmountThanPoolReserves);
        (out, curve, l, p, c, curve + l + p + c)
    };
    let buyback_bps = a.global_config.buyback_basis_points;
    let calculate_buyback = || {
        u64::try_from((protocol_fee as u128) * (buyback_bps as u128) / 10000)
            .expect("buyback fee fits u64")
    };
    let buyback_fee = if sell { calculate_buyback() } else { 0 };
    let quote_transfer_fee = if sell {
        crate::quote_transfer_fee(&h.quote_mint.to_account_info(), total_quote, false)?
    } else {
        input_tf
    };
    let output = if sell {
        total_quote
            .checked_sub(quote_transfer_fee)
            .ok_or(PumpAmmError::Overflow)?
    } else {
        base_amount
    };
    let seeds = pool_seed_parts(&h.pool);
    if last {
        if sell {
            transfer(
                quote_program.clone(),
                h.quote_mint.to_account_info(),
                h.pool_quote_token_account.to_account_info(),
                a.user_out_token_account.to_account_info(),
                h.pool.to_account_info(),
                total_quote,
                h.quote_mint.decimals,
                &seeds,
            )?;
        } else {
            transfer(
                base_program,
                h.base_mint.to_account_info(),
                h.pool_base_token_account.to_account_info(),
                a.user_out_token_account.to_account_info(),
                h.pool.to_account_info(),
                base_amount,
                h.base_mint.decimals,
                &seeds,
            )?;
        }
    }
    let buyback_fee = if sell {
        buyback_fee
    } else {
        calculate_buyback()
    };
    let buyback_received = buyback_fee
        .checked_sub(crate::quote_transfer_fee(
            &h.quote_mint.to_account_info(),
            buyback_fee,
            false,
        )?)
        .ok_or(PumpAmmError::Overflow)?;
    let protocol_accrual = protocol_fee
        .checked_sub(buyback_fee)
        .expect("buyback_fee never exceeds protocol_fee");
    let accrued = protocol_accrual
        .checked_add(creator_fee)
        .ok_or(PumpAmmError::Overflow)?;
    h.pool.protocol_fees = h
        .pool
        .protocol_fees
        .checked_add(protocol_accrual)
        .ok_or(PumpAmmError::Overflow)?;
    h.pool.creator_fees = h
        .pool
        .creator_fees
        .checked_add(creator_fee)
        .ok_or(PumpAmmError::Overflow)?;
    h.pool.virtual_quote_reserves = old_virtual
        .checked_sub(accrued as i128)
        .ok_or(PumpAmmError::Overflow)?;
    if buyback_fee > 0 {
        transfer(
            quote_program,
            h.quote_mint.to_account_info(),
            h.pool_quote_token_account.to_account_info(),
            a.buyback_fee_recipient.to_account_info(),
            h.pool.to_account_info(),
            buyback_fee,
            h.quote_mint.decimals,
            &seeds,
        )?;
    }
    let user_base_balance = if sell {
        user_input_balance
    } else {
        user_output_balance
    };
    let user_quote_balance = if sell {
        user_output_balance
    } else {
        user_input_balance
    };
    let user_base = if sell && first {
        a.user_in_token_account.key()
    } else if !sell && last {
        a.user_out_token_account.key()
    } else {
        Pubkey::default()
    };
    let user_quote = if !sell && first {
        a.user_in_token_account.key()
    } else if sell && last {
        a.user_out_token_account.key()
    } else {
        Pubkey::default()
    };
    if sell {
        emit_event(
            a,
            SellEvent {
                timestamp: Clock::get()?.unix_timestamp,
                base_amount_in: base_amount,
                min_quote_amount_out: minimum,
                user_base_token_reserves: user_base_balance,
                user_quote_token_reserves: user_quote_balance,
                pool_base_token_reserves: b,
                pool_quote_token_reserves: raw_q,
                quote_amount_out: curve_quote,
                lp_fee_basis_points: selected.lp_fee_bps,
                lp_fee,
                protocol_fee_basis_points: selected.protocol_fee_bps,
                protocol_fee,
                quote_amount_out_without_lp_fee: curve_quote - lp_fee,
                user_quote_amount_out: total_quote,
                pool: h.pool.key(),
                user: a.user.key(),
                user_base_token_account: user_base,
                user_quote_token_account: user_quote,
                protocol_fee_recipient: Pubkey::default(),
                protocol_fee_recipient_token_account: Pubkey::default(),
                coin_creator: h.pool.coin_creator,
                coin_creator_fee_basis_points: selected.creator_fee_bps,
                coin_creator_fee: creator_fee,
                cashback_fee_basis_points: 0,
                cashback: 0,
                buyback_fee_basis_points: buyback_bps,
                buyback_fee: buyback_received,
                virtual_quote_reserves: old_virtual,
                can_boost,
                base_supply: h.base_mint.supply,
                holder_rewards_bps: if h.pool.is_holder_reward {
                    selected.creator_fee_bps
                } else {
                    0
                },
                holder_rewards: if h.pool.is_holder_reward {
                    creator_fee
                } else {
                    0
                },
                creator_fee_unclaimed: h.pool.creator_fees,
                quote_transfer_fee,
            },
        )?;
    } else {
        emit_event(
            a,
            BuyEvent {
                timestamp: Clock::get()?.unix_timestamp,
                base_amount_out: base_amount,
                max_quote_amount_in: amount,
                user_base_token_reserves: user_base_balance,
                user_quote_token_reserves: user_quote_balance,
                pool_base_token_reserves: b,
                pool_quote_token_reserves: raw_q,
                quote_amount_in: amount,
                lp_fee_basis_points: selected.lp_fee_bps,
                lp_fee,
                protocol_fee_basis_points: selected.protocol_fee_bps,
                protocol_fee,
                quote_amount_in_with_lp_fee: curve_quote + lp_fee,
                user_quote_amount_in: curve_quote,
                pool: h.pool.key(),
                user: a.user.key(),
                user_base_token_account: user_base,
                user_quote_token_account: user_quote,
                protocol_fee_recipient: Pubkey::default(),
                protocol_fee_recipient_token_account: Pubkey::default(),
                coin_creator: h.pool.coin_creator,
                coin_creator_fee_basis_points: selected.creator_fee_bps,
                coin_creator_fee: creator_fee,
                track_volume: false,
                total_unclaimed_tokens: a.user_volume_accumulator.total_unclaimed_tokens,
                total_claimed_tokens: a.user_volume_accumulator.total_claimed_tokens,
                current_sol_volume: a.user_volume_accumulator.current_sol_volume,
                last_update_timestamp: a.user_volume_accumulator.last_update_timestamp,
                min_base_amount_out: minimum,
                ix_name: "multi_hop_swap".into(),
                cashback_fee_basis_points: 0,
                cashback: 0,
                buyback_fee_basis_points: buyback_bps,
                buyback_fee: buyback_received,
                virtual_quote_reserves: old_virtual,
                can_boost,
                base_supply: h.base_mint.supply,
                holder_rewards_bps: if h.pool.is_holder_reward {
                    selected.creator_fee_bps
                } else {
                    0
                },
                holder_rewards: if h.pool.is_holder_reward {
                    creator_fee
                } else {
                    0
                },
                creator_fee_unclaimed: h.pool.creator_fees,
                quote_transfer_fee,
            },
        )?;
    }
    Ok(output)
}
