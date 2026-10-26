//! Partial PumpSwap reconstruction. Only explicitly implemented handlers exist.
//! This crate is not the historical source or a byte-identical replacement.
use anchor_lang::prelude::*;
mod state;
mod instructions;
use instructions::admin::create_config::*;
pub use instructions::token_incentives::init_user_volume_accumulator::InitUserVolumeAccumulator;
use instructions::token_incentives::*;
mod legacy_buy;
use legacy_buy::*;
mod legacy_sell;
use legacy_sell::*;
mod cashback;
use cashback::*;
mod incentives;
use incentives::*;
mod creator_reassignment;
use creator_reassignment::*;
mod multi_hop;
use multi_hop::*;
mod trade;
mod create;
mod boost;
mod boost_burn;
mod sweep;
mod extend;
mod collect;
mod transfer_creator;
use transfer_creator::*;
use collect::*;
use extend::*;
use sweep::*;
use boost::*;
use boost_burn::*;
use create::*;
use trade::*;
use anchor_spl::{token::Token, token_2022::Token2022, token_interface::{self, Mint, TokenAccount}};
use state::*;

declare_id!("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA");

#[program]
pub mod pump_amm_recovered {
    use super::*;
    // Static-only reconstruction: no authentic successful initializer replay exists.
    pub fn create_config(ctx: Context<CreateConfig>, lp_fee_basis_points: u64,
        protocol_fee_basis_points: u64, protocol_fee_recipients: [Pubkey; 8],
        coin_creator_fee_basis_points: u64, admin_set_coin_creator_authority: Pubkey) -> Result<()> {
        let admin = ctx.accounts.admin.key();
        let global_config = &mut ctx.accounts.global_config;
        global_config.admin = admin;
        global_config.set_lp_fee_basis_points(lp_fee_basis_points)?;
        global_config.set_protocol_fee_basis_points(protocol_fee_basis_points)?;
        global_config.set_protocol_fee_recipients(protocol_fee_recipients)?;
        global_config.set_coin_creator_fee_basis_points(coin_creator_fee_basis_points)?;
        global_config.disable_flags = 0;
        global_config.admin_set_coin_creator_authority = admin_set_coin_creator_authority;
        let event = CreateConfigEvent { timestamp: Clock::get()?.unix_timestamp,
            admin, lp_fee_basis_points, protocol_fee_basis_points,
            protocol_fee_recipients, coin_creator_fee_basis_points,
            admin_set_coin_creator_authority };
        emit!(event);
        emit_cpi!(event);
        Ok(())
    }

    pub fn multi_hop_swap<'info>(ctx:Context<'_, '_, 'info, 'info, MultiHop<'info>>,amount_in:u64,min_amount_out:u64)->Result<()>{multi_hop::execute(ctx,amount_in,min_amount_out)}
    pub fn buy<'info>(ctx:Context<'_,'_,'_,'info,LegacyBuy<'info>>,base_amount_out:u64,max_quote_amount_in:u64,track_volume:OptionBool)->Result<()>{legacy_buy::execute(ctx,base_amount_out,max_quote_amount_in,track_volume.0,false)}
    pub fn buy_exact_quote_in<'info>(ctx:Context<'_,'_,'_,'info,LegacyBuy<'info>>,spendable_quote_in:u64,min_base_amount_out:u64,track_volume:OptionBool)->Result<()>{legacy_buy::execute(ctx,spendable_quote_in,min_base_amount_out,track_volume.0,true)}
    pub fn sell<'info>(ctx:Context<'_,'_,'_,'info,LegacySell<'info>>,base_amount_in:u64,min_quote_amount_out:u64)->Result<()>{legacy_sell::execute(ctx,base_amount_in,min_quote_amount_out)}
    pub fn claim_cashback(ctx:Context<ClaimCashback>)->Result<()>{cashback::claim(ctx)}
    pub fn sync_user_volume_accumulator(ctx:Context<SyncUserVolumeAccumulator>)->Result<()>{incentives::sync(ctx)}
    pub fn admin_update_token_incentives(ctx:Context<AdminUpdateTokenIncentives>,start_time:i64,end_time:i64,seconds_in_a_day:i64,day_number:u64,token_supply_per_day:u64)->Result<()>{incentives::admin(ctx,start_time,end_time,seconds_in_a_day,day_number,token_supply_per_day)}
    pub fn claim_token_incentives(ctx:Context<ClaimTokenIncentives>)->Result<()>{incentives::claim(ctx)}
    pub fn admin_cto_pool(ctx:Context<AdminCtoPool>,coin_creator:Pubkey,is_holder_reward:bool,creator_fee_bps:Option<u64>)->Result<()>{creator_reassignment::admin_cto(ctx,coin_creator,is_holder_reward,creator_fee_bps)}
    pub fn migrate_pool_coin_creator(ctx:Context<MigratePoolCoinCreator>)->Result<()>{creator_reassignment::migrate(ctx)}
    pub fn set_coin_creator(ctx:Context<SetCoinCreator>)->Result<()>{creator_reassignment::set(ctx)}

    pub fn transfer_creator_fees_to_pump(ctx: Context<TransferCreatorFeesToPump>) -> Result<()> { transfer_creator::legacy(ctx) }
    pub fn transfer_creator_fees_to_pump_v2(ctx: Context<TransferCreatorFeesToPumpV2>) -> Result<()> { transfer_creator::v2(ctx) }

    pub fn collect_coin_creator_fee(ctx: Context<CollectCoinCreatorFee>) -> Result<()> { collect::execute(ctx) }

    pub fn extend_account(ctx: Context<ExtendAccount>) -> Result<()> { extend::execute(ctx) }

    pub fn sweep_protocol_fee(ctx: Context<SweepFees>) -> Result<()> { sweep::execute(ctx,false) }
    pub fn sweep_creator_fee(ctx: Context<SweepFees>) -> Result<()> { sweep::execute(ctx,true) }

    pub fn boost_buy_and_burn(ctx: Context<BoostBuyAndBurn>, quote_amount_in: u64, min_base_amount_burned: u64) -> Result<()> { boost_burn::execute(ctx, quote_amount_in, min_base_amount_burned) }
    pub fn init_boost(ctx: Context<InitBoost>) -> Result<()> { boost::execute(ctx) }

    pub fn create_pool(ctx: Context<CreatePool>, index: u16, base_amount_in: u64, quote_amount_in: u64, coin_creator: Pubkey, is_mayhem_mode: bool, is_cashback_coin: OptionBool, creator_fee_bps: OptionU64, can_edit_creator_fee: OptionBool, is_holder_reward: OptionBool) -> Result<()> { create::execute(ctx,index,base_amount_in,quote_amount_in,coin_creator,is_mayhem_mode,is_cashback_coin.0,creator_fee_bps.0,can_edit_creator_fee.0,is_holder_reward.0) }

    pub fn buy_v2(ctx: Context<TradeV2>, base_amount_out: u64, max_quote_amount_in: u64) -> Result<()> { trade::execute(ctx, base_amount_out, max_quote_amount_in, 0) }
    pub fn sell_v2(ctx: Context<TradeV2>, base_amount_in: u64, min_quote_amount_out: u64) -> Result<()> { trade::execute(ctx, base_amount_in, min_quote_amount_out, 1) }
    pub fn buy_exact_quote_in_v2(ctx: Context<TradeV2>, spendable_quote_in: u64, min_base_amount_out: u64) -> Result<()> { trade::execute(ctx, spendable_quote_in, min_base_amount_out, 2) }
    pub fn deposit(ctx: Context<Liquidity>, lp_token_amount_out: u64, max_base_amount_in: u64, max_quote_amount_in: u64) -> Result<()> {
        liquidity(ctx, lp_token_amount_out, max_base_amount_in, max_quote_amount_in, true)
    }
    pub fn withdraw(ctx: Context<Liquidity>, lp_token_amount_in: u64, min_base_amount_out: u64, min_quote_amount_out: u64) -> Result<()> {
        liquidity(ctx, lp_token_amount_in, min_base_amount_out, min_quote_amount_out, false)
    }

    pub fn init_user_volume_accumulator(ctx: Context<InitUserVolumeAccumulator>) -> Result<()> {
        let event = InitUserVolumeAccumulatorEvent { payer: ctx.accounts.payer.key(),
            user: ctx.accounts.user.key(), timestamp: Clock::get()?.unix_timestamp };
        ctx.accounts.user_volume_accumulator.user = ctx.accounts.user.key();
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }
    pub fn close_user_volume_accumulator(ctx: Context<CloseUserVolumeAccumulator>) -> Result<()> {
        let account = &ctx.accounts.user_volume_accumulator;
        let event = CloseUserVolumeAccumulatorEvent { user: ctx.accounts.user.key(),
            timestamp: Clock::get()?.unix_timestamp, total_unclaimed_tokens: account.total_unclaimed_tokens,
            total_claimed_tokens: account.total_claimed_tokens, current_sol_volume: account.current_sol_volume,
            last_update_timestamp: account.last_update_timestamp };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }

    pub fn set_reserved_fee_recipients(ctx: Context<SetReservedFeeRecipients>, whitelist_pda: Pubkey) -> Result<()> {
        require!(ctx.remaining_accounts.len() >= 8, PumpAmmError::NotEnoughRemainingAccounts);
        let mut recipients = [Pubkey::default(); 8];
        for i in 0..8 {
            recipients[i] = ctx.remaining_accounts[i].key();
            require_keys_neq!(recipients[i], Pubkey::default(), PumpAmmError::AllProtocolFeeRecipientsShouldBeNonZero);
        }
        ctx.accounts.global_config.whitelist_pda = whitelist_pda;
        ctx.accounts.global_config.reserved_fee_recipient = recipients[0];
        ctx.accounts.global_config.reserved_fee_recipients.copy_from_slice(&recipients[1..]);
        let event = ReservedFeeRecipientsEvent { timestamp: Clock::get()?.unix_timestamp,
            reserved_fee_recipient: recipients[0], reserved_fee_recipients: recipients[1..].try_into().unwrap() };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }

    pub fn update_creator_fee_config(ctx: Context<UpdateCreatorFeeConfig>, creator_fee_configurable: bool,
        max_configurable_creator_fee_bps: u64) -> Result<()> {
        let account = ctx.accounts.global_config.to_account_info();
        if account.data_len() < 949 {
            let required = Rent::get()?.minimum_balance(949);
            let top_up = required.saturating_sub(account.lamports());
            if top_up > 0 {
                anchor_lang::system_program::transfer(CpiContext::new(
                    ctx.accounts.system_program.to_account_info(),
                    anchor_lang::system_program::Transfer {
                        from: ctx.accounts.admin.to_account_info(), to: account.clone(),
                    }), top_up)?;
            }
            account.realloc(949, false)?;
        }
        ctx.accounts.global_config.creator_fee_configurable = creator_fee_configurable;
        ctx.accounts.global_config.max_configurable_creator_fee_bps = max_configurable_creator_fee_bps;
        let event = UpdateCreatorFeeConfigEvent { timestamp: Clock::get()?.unix_timestamp,
            admin: ctx.accounts.admin.key(), creator_fee_configurable, max_configurable_creator_fee_bps };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }

    pub fn set_boost_authority(ctx: Context<SetBoostAuthority>) -> Result<()> {
        let account = ctx.accounts.global_config.to_account_info();
        if account.data_len() < 949 {
            let required = Rent::get()?.minimum_balance(949);
            let top_up = required.saturating_sub(account.lamports());
            if top_up > 0 {
                anchor_lang::system_program::transfer(CpiContext::new(
                    ctx.accounts.system_program.to_account_info(),
                    anchor_lang::system_program::Transfer {
                        from: ctx.accounts.admin.to_account_info(), to: account.clone(),
                    }), top_up)?;
            }
            account.realloc(949, false)?;
        }
        let old_boost_authority = ctx.accounts.global_config.boost_authority;
        let new_boost_authority = ctx.accounts.boost_authority.key();
        ctx.accounts.global_config.boost_authority = new_boost_authority;
        let event = SetBoostAuthorityEvent { timestamp: Clock::get()?.unix_timestamp,
            admin: ctx.accounts.admin.key(), old_boost_authority, new_boost_authority };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }

    pub fn update_fee_config(ctx: Context<AdminGlobal>, lp_fee_basis_points: u64,
        protocol_fee_basis_points: u64, protocol_fee_recipients: [Pubkey; 8],
        coin_creator_fee_basis_points: u64, admin_set_coin_creator_authority: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.global_config;
        config.set_lp_fee_basis_points(lp_fee_basis_points)?;
        config.set_protocol_fee_basis_points(protocol_fee_basis_points)?;
        config.set_protocol_fee_recipients(protocol_fee_recipients)?;
        config.set_coin_creator_fee_basis_points(coin_creator_fee_basis_points)?;
        config.admin_set_coin_creator_authority = admin_set_coin_creator_authority;
        let event = UpdateFeeConfigEvent { timestamp: Clock::get()?.unix_timestamp,
            admin: ctx.accounts.admin.key(), lp_fee_basis_points, protocol_fee_basis_points,
            protocol_fee_recipients, coin_creator_fee_basis_points, admin_set_coin_creator_authority };
        emit!(event);
        emit_cpi!(event);
        Ok(())
    }

    pub fn update_buyback_config(ctx: Context<AdminGlobal>, buyback_basis_points: Option<u64>) -> Result<()> {
        if let Some(bps) = buyback_basis_points {
            require!(bps <= 10_000, PumpAmmError::BuybackBasisPointsOutOfRange);
            ctx.accounts.global_config.buyback_basis_points = bps;
        }
        if !ctx.remaining_accounts.is_empty() {
            require_eq!(ctx.remaining_accounts.len(), 8, PumpAmmError::WrongBuybackFeeRecipientsCount);
            let mut recipients = [Pubkey::default(); 8];
            for (i, account) in ctx.remaining_accounts.iter().enumerate() { recipients[i] = account.key(); }
            for recipient in recipients.iter() { require_keys_neq!(*recipient, Pubkey::default(), PumpAmmError::AllBuybackFeeRecipientsShouldBeNonZero); }
            for i in 0..8 { for j in 0..i { require_keys_neq!(recipients[i], recipients[j], PumpAmmError::NotUniqueBuybackFeeRecipients); } }
            ctx.accounts.global_config.buyback_fee_recipients = recipients;
        }
        Ok(())
    }

    pub fn toggle_mayhem_mode(ctx: Context<AdminGlobal>, enabled: bool) -> Result<()> {
        require_neq!(ctx.accounts.global_config.mayhem_mode_enabled, enabled, PumpAmmError::MayhemModeInDesiredState);
        ctx.accounts.global_config.mayhem_mode_enabled = enabled;
        Ok(())
    }
    pub fn toggle_cashback_enabled(ctx: Context<AdminGlobal>, enabled: bool) -> Result<()> {
        require_neq!(ctx.accounts.global_config.is_cashback_enabled, enabled, PumpAmmError::CashbackNotInDesiredState);
        ctx.accounts.global_config.is_cashback_enabled = enabled;
        Ok(())
    }
    pub fn toggle_boost(ctx: Context<AdminGlobalNoEvent>, enabled: bool) -> Result<()> {
        require_keys_neq!(ctx.accounts.global_config.boost_authority, Pubkey::default(), PumpAmmError::InvalidAdmin);
        ctx.accounts.global_config.boost_enabled = enabled;
        Ok(())
    }

    pub fn update_admin(ctx: Context<UpdateAdmin>) -> Result<()> {
        let admin = ctx.accounts.global_config.admin;
        let new_admin = ctx.accounts.new_admin.key();
        ctx.accounts.global_config.admin = new_admin;
        let event = UpdateAdminEvent { timestamp: Clock::get()?.unix_timestamp, admin, new_admin };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }

    pub fn disable(ctx: Context<AdminGlobal>, disable_create_pool: bool,
        disable_deposit: bool, disable_withdraw: bool,
        disable_buy: bool, disable_sell: bool) -> Result<()> {
        let flags = &mut ctx.accounts.global_config.disable_flags;
        *flags = (*flags & !1) | u8::from(disable_create_pool);
        *flags = (*flags & !2) | (u8::from(disable_deposit) << 1);
        *flags = (*flags & !4) | (u8::from(disable_withdraw) << 2);
        *flags = (*flags & !8) | (u8::from(disable_buy) << 3);
        *flags = (*flags & !16) | (u8::from(disable_sell) << 4);
        let event = DisableEvent { timestamp: Clock::get()?.unix_timestamp,
            admin: ctx.accounts.admin.key(), disable_create_pool,
            disable_deposit, disable_withdraw, disable_buy, disable_sell };
        emit!(event.clone());
        emit_cpi!(event);
        Ok(())
    }
}

#[event_cpi]
#[derive(Accounts)]
pub struct AdminGlobal<'info> {
    pub admin: Signer<'info>,
    #[account(mut, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
}

#[error_code]
pub enum PumpAmmError {
    FeeBasisPointsExceedsMaximum = 0,
    ZeroBaseAmount = 1,
    ZeroQuoteAmount = 2,
    TooLittlePoolTokenLiquidity = 3,
    ExceededSlippage = 4,
    InvalidAdmin = 5,
    UnsupportedBaseMint = 6,
    UnsupportedQuoteMint = 7,
    InvalidBaseMint = 8,
    InvalidQuoteMint = 9,
    InvalidLpMint = 10,
    AllProtocolFeeRecipientsShouldBeNonZero = 11,
    UnsortedNotUniqueProtocolFeeRecipients = 12,
    InvalidProtocolFeeRecipient = 13,
    InvalidPoolBaseTokenAccount = 14,
    InvalidPoolQuoteTokenAccount = 15,
    BuyMoreBaseAmountThanPoolReserves = 16,
    DisabledCreatePool = 17,
    DisabledDeposit = 18,
    DisabledWithdraw = 19,
    DisabledBuy = 20,
    DisabledSell = 21,
    SameMint = 22,
    Overflow = 23,
    Truncation = 24,
    DivisionByZero = 25,
    NewSizeLessThanCurrentSize = 26,
    AccountTypeNotSupported = 27,
    OnlyCanonicalPumpPoolsCanHaveCoinCreator = 28,
    InvalidAdminSetCoinCreatorAuthority = 29,
    StartTimeInThePast = 30,
    EndTimeInThePast = 31,
    EndTimeBeforeStartTime = 32,
    TimeRangeTooLarge = 33,
    EndTimeBeforeCurrentDay = 34,
    SupplyUpdateForFinishedRange = 35,
    DayIndexAfterEndIndex = 36,
    DayInActiveRange = 37,
    InvalidIncentiveMint = 38,
    #[msg("buy: Not enough quote tokens to cover for fees.")]
    BuyNotEnoughQuoteTokensToCoverFees = 39,
    #[msg("buy: slippage - would buy less tokens than expected min_base_amount_out")]
    BuySlippageBelowMinBaseAmountOut = 40,
    MayhemModeDisabled = 41,
    OnlyPumpPoolsMayhemMode = 42,
    MayhemModeInDesiredState = 43,
    NotEnoughRemainingAccounts = 44,
    InvalidSharingConfigBaseMint = 45,
    InvalidSharingConfigCoinCreator = 46,
    #[msg("coin creator has been migrated to sharing config")]
    CoinCreatorMigratedToSharingConfig = 47,
    #[msg("creator_vault has been migrated to sharing config, use pump:distribute_creator_fees instead")]
    CreatorVaultMigratedToSharingConfig = 48,
    #[msg("Cashback is disabled")]
    CashbackNotEnabled = 49,
    OnlyPumpPoolsCashback = 50,
    CashbackNotInDesiredState = 51,
    TokensInVaultLessThanCashbackEarned = 52,
    #[msg("Buyback fee recipient not authorized")]
    BuybackFeeRecipientNotAuthorized = 53,
    AllBuybackFeeRecipientsShouldBeNonZero = 54,
    NotUniqueBuybackFeeRecipients = 55,
    #[msg("buyback_basis_points must be <= 10_000")]
    BuybackBasisPointsOutOfRange = 56,
    #[msg("buyback fee recipients require exactly 8 remaining accounts (or none)")]
    WrongBuybackFeeRecipientsCount = 57,
    BuybackFeeRecipientMissing = 58,
    #[msg("Cashback trade is missing the required remaining accounts")]
    MissingCashbackAccounts = 59,
    #[msg("Cashback user_volume_accumulator account is invalid")]
    InvalidCashbackAccumulator = 60,
    #[msg("Cashback user_volume_accumulator ATA is missing or invalid")]
    InvalidCashbackAccumulatorAta = 61,
    #[msg("pool_v2 remaining account is missing or invalid")]
    InvalidPoolV2 = 62,
    #[msg("BOOST: sell output exceeds the real quote vault. effective = real + virtual is pricing-only; payout is capped at real_vault, so quote min(out, real_vault)")]
    InsufficientRealQuoteReserves = 63,
    #[msg("BOOST: deposit/withdraw don't apply to boost pools")]
    BoostPoolLiquidityUnsupported = 64,
    #[msg("BOOST: pool cannot be boosted (no virtual reserves)")]
    PoolCannotBoost = 65,
    #[msg("BOOST: boost is disabled")]
    BoostDisabled = 66,
    #[msg("BOOST: lp_supply must never drop below the circulating LP mint supply")]
    SeedLockViolation = 67,
    #[msg("Configurable creator fee is disabled")]
    CreatorFeeNotConfigurable = 68,
    #[msg("Creator fee basis points must be between 1 and the configured maximum")]
    CreatorFeeBpsOutOfRange = 69,
    #[msg("Creator fee is not editable for this pool")]
    CreatorFeeNotEditable = 70,
    #[msg("Cashback coins cannot have a creator fee")]
    CreatorFeeNotAllowedForCashbackCoin = 71,
    #[msg("Sharing config is not active")]
    SharingConfigNotActive = 72,
    #[msg("Not authorized")]
    NotAuthorized = 73,
    #[msg("The coin creator of a holder-reward pool cannot be changed")]
    HolderRewardCreatorImmutable = 74,
    #[msg("CTO is not allowed on a mayhem-mode pool")]
    CtoNotAllowedForMayhemPool = 75,
    #[msg("A holder-reward pool's coin creator must be the holder-rewards PDA")]
    InvalidHolderRewardCoinCreator = 76,
    #[msg("Creator fee is not configurable on a SOL or USDC quote; the fee schedule applies")]
    CreatorFeeNotConfigurableForQuote = 77,
    #[msg("Only canonical pump pools are supported by this instruction")]
    OnlyPumpPools = 78,
    #[msg("v2 trades do not support cashback coins; use the v1 instructions")]
    CashbackCoinNotSupported = 79,
    #[msg("v2 trades do not support mayhem-mode pools; use the v1 instructions")]
    MayhemPoolNotSupported = 80,
    #[msg("creator_fees must be swept before the coin creator changes")]
    CreatorFeesNotSwept = 81,
    #[msg("The fee config tier table is empty")]
    FeeTiersEmpty = 82,
    #[msg("The fee config account is shorter than its initialize size")]
    FeeConfigTooShort = 83,
    #[msg("multi-hop: a hop's input mint is neither side of its pool or curve, or the route does not end in user_out_token_account's mint")]
    MultiHopDiscontinuousPath = 84,
    #[msg("multi-hop: the balances around the bonding-curve hops do not match the amounts pump reported")]
    MultiHopCurveRunMismatch = 85,
    #[msg("multi-hop: every hop must trade in the same direction, all buys or all sells")]
    MultiHopMixedDirection = 86,
    #[msg("A transfer's source is its destination and the signer does not own it")]
    SelfTransferNotAllowed = 87,
    #[msg("quote_mint must be writable for a quote with a Token-2022 transfer fee: its withheld fees are harvested to the mint.")]
    QuoteMintNotWritable = 88,
}

#[event_cpi]
#[derive(Accounts)]
pub struct UpdateAdmin<'info> {
    pub admin: Signer<'info>,
    #[account(mut, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    /// CHECK: Only this account's public key is stored as the new admin.
    pub new_admin: UncheckedAccount<'info>,
}

#[derive(Accounts)]
pub struct AdminGlobalNoEvent<'info> {
    pub admin: Signer<'info>,
    #[account(mut, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
}

#[event_cpi]
#[derive(Accounts)]
pub struct SetBoostAuthority<'info> {
    pub admin: Signer<'info>,
    #[account(mut, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    /// CHECK: Only its public key is stored as authority.
    pub boost_authority: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
}

#[event_cpi]
#[derive(Accounts)]
pub struct UpdateCreatorFeeConfig<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(mut, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    pub system_program: Program<'info, System>,
}

#[event_cpi]
#[derive(Accounts)]
pub struct SetReservedFeeRecipients<'info> {
    #[account(mut, seeds = [b"global_config"], bump, has_one = admin @ PumpAmmError::InvalidAdmin)]
    pub global_config: Box<Account<'info, GlobalConfig>>,
    pub admin: Signer<'info>,
}

#[event_cpi]
#[derive(Accounts)]
pub struct CloseUserVolumeAccumulator<'info> {
    #[account(mut)]
    pub user: Signer<'info>,
    #[account(mut, close = user, seeds = [b"user_volume_accumulator", user.key().as_ref()], bump)]
    pub user_volume_accumulator: Account<'info, UserVolumeAccumulator>,
}

#[event_cpi]
#[derive(Accounts)]
pub struct Liquidity<'info> {
    #[account(mut, has_one = base_mint @ PumpAmmError::InvalidBaseMint, has_one = quote_mint @ PumpAmmError::InvalidQuoteMint, has_one = lp_mint @ PumpAmmError::InvalidLpMint, has_one = pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount, has_one = pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    pub global_config: Box<Account<'info, GlobalConfig>>,
    pub user: Signer<'info>,
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)]
    pub lp_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)]
    pub user_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub user_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut, token::authority = user)]
    pub user_pool_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
    pub token_2022_program: Program<'info, Token2022>,
}
fn liquidity(ctx: Context<Liquidity>, amount: u64, base_limit: u64, quote_limit: u64, deposit: bool) -> Result<()> {
    let a = &mut *ctx.accounts;
    if deposit { require!(a.global_config.disable_flags & 2 == 0, PumpAmmError::DisabledDeposit); }
    else {
        require!(a.global_config.disable_flags & 4 == 0, PumpAmmError::DisabledWithdraw);
        require!(a.lp_mint.supply <= a.pool.lp_supply, PumpAmmError::SeedLockViolation);
    }
    let old_supply = a.pool.lp_supply;
    let base_reserve = a.pool_base_token_account.amount;
    let fees = a.pool.protocol_fees.checked_add(a.pool.creator_fees).ok_or(PumpAmmError::Overflow)?;
    let quote_reserve = a.pool_quote_token_account.amount.checked_sub(fees).ok_or(PumpAmmError::Overflow)?;
    let ratio = |reserve: u64| -> Result<u64> {
        let mut n = (reserve as u128).checked_mul(amount as u128).ok_or(PumpAmmError::Overflow)?;
        if deposit { n = n.checked_add(old_supply as u128).ok_or(PumpAmmError::Overflow)?.checked_sub(1).ok_or(PumpAmmError::Overflow)?; }
        let n = n.checked_div(old_supply as u128).ok_or(PumpAmmError::DivisionByZero)?;
        u64::try_from(n).map_err(|_| error!(PumpAmmError::Truncation))
    };
    let base_amount = ratio(base_reserve)?;
    let quote_amount = ratio(quote_reserve)?;
    let quote_transfer_fee = quote_transfer_fee(&a.quote_mint.to_account_info(), quote_amount, deposit)?;
    let quote_transfer_amount = if deposit { quote_amount.checked_add(quote_transfer_fee) } else { Some(quote_amount) }.ok_or(PumpAmmError::Overflow)?;
    let quote_received = quote_amount.checked_sub(if deposit { 0 } else { quote_transfer_fee }).ok_or(PumpAmmError::Overflow)?;
    if deposit { require!(base_amount <= base_limit && quote_transfer_amount <= quote_limit, PumpAmmError::ExceededSlippage); }
    else { require!(base_amount >= base_limit && quote_received >= quote_limit, PumpAmmError::ExceededSlippage); }
    let index = a.pool.index.to_le_bytes(); let bump = [a.pool.pool_bump];
    let creator = a.pool.creator; let base = a.pool.base_mint; let quote = a.pool.quote_mint;
    let seeds: &[&[u8]] = &[b"pool", &index, creator.as_ref(), base.as_ref(), quote.as_ref(), &bump];
    let signer_seeds = [seeds];
    for (mint, user, vault, quantity) in [(&a.base_mint, &a.user_base_token_account, &a.pool_base_token_account, base_amount), (&a.quote_mint, &a.user_quote_token_account, &a.pool_quote_token_account, quote_transfer_amount)] {
        if quantity == 0 { continue; }
        if user.key() == vault.key() {
            require!(user.owner == if deposit { a.user.key() } else { a.pool.key() }, PumpAmmError::SelfTransferNotAllowed);
        }
        let program = if *mint.to_account_info().owner == anchor_spl::token::ID { a.token_program.to_account_info() } else { a.token_2022_program.to_account_info() };
        let transfer = token_interface::TransferChecked { from: if deposit { user.to_account_info() } else { vault.to_account_info() },
            mint: mint.to_account_info(), to: if deposit { vault.to_account_info() } else { user.to_account_info() },
            authority: if deposit { a.user.to_account_info() } else { a.pool.to_account_info() } };
        token_interface::transfer_checked(CpiContext::new_with_signer(program, transfer, if deposit { &[] } else { &signer_seeds }), quantity, mint.decimals)?;
    }
    if deposit {
        token_interface::mint_to(CpiContext::new_with_signer(a.token_2022_program.to_account_info(), token_interface::MintTo {
            mint: a.lp_mint.to_account_info(), to: a.user_pool_token_account.to_account_info(), authority: a.pool.to_account_info() }, &[seeds]), amount)?;
    } else {
        token_interface::burn(CpiContext::new(a.token_2022_program.to_account_info(), token_interface::Burn {
            mint: a.lp_mint.to_account_info(), from: a.user_pool_token_account.to_account_info(), authority: a.user.to_account_info() }), amount)?;
    }
    let new_supply = if deposit { old_supply.checked_add(amount) } else { old_supply.checked_sub(amount) }.ok_or(PumpAmmError::Overflow)?;
    let effective_virtual = a.pool.virtual_quote_reserves.checked_add(fees as i128).ok_or(PumpAmmError::Overflow)?;
    if effective_virtual != 0 {
        let virtual_reserve = u128::try_from(effective_virtual).map_err(|_| error!(PumpAmmError::Overflow))?;
        let mut change = virtual_reserve.checked_mul(amount as u128).ok_or(PumpAmmError::Overflow)?;
        if !deposit { change = change.checked_add(old_supply as u128).ok_or(PumpAmmError::Overflow)?.checked_sub(1).ok_or(PumpAmmError::Overflow)?; }
        change = change.checked_div(old_supply as u128).ok_or(PumpAmmError::DivisionByZero)?;
        if !deposit { u64::try_from(change).map_err(|_| error!(PumpAmmError::Truncation))?; }
        let change = i128::try_from(change).map_err(|_| error!(PumpAmmError::Overflow))?;
        a.pool.virtual_quote_reserves = if deposit { a.pool.virtual_quote_reserves.checked_add(change) } else { a.pool.virtual_quote_reserves.checked_sub(change) }.ok_or(PumpAmmError::Overflow)?;
    }
    a.pool.lp_supply = new_supply;
    if deposit {
        let event = DepositEvent {
            timestamp: Clock::get()?.unix_timestamp,
            lp_token_amount_out: amount,
            max_base_amount_in: base_limit,
            max_quote_amount_in: quote_limit,
            user_base_token_reserves: a.user_base_token_account.amount,
            user_quote_token_reserves: a.user_quote_token_account.amount,
            pool_base_token_reserves: base_reserve,
            pool_quote_token_reserves: a.pool_quote_token_account.amount,
            base_amount_in: base_amount,
            quote_amount_in: quote_amount,
            lp_mint_supply: old_supply,
            pool: a.pool.key(),
            user: a.user.key(),
            user_base_token_account: a.user_base_token_account.key(),
            user_quote_token_account: a.user_quote_token_account.key(),
            user_pool_token_account: a.user_pool_token_account.key(),
            quote_transfer_fee,
        };
        emit!(event.clone());
        emit_cpi!(event);
    } else {
        let event = WithdrawEvent {
            timestamp: Clock::get()?.unix_timestamp,
            lp_token_amount_in: amount,
            min_base_amount_out: base_limit,
            min_quote_amount_out: quote_limit,
            user_base_token_reserves: a.user_base_token_account.amount,
            user_quote_token_reserves: a.user_quote_token_account.amount,
            pool_base_token_reserves: base_reserve,
            pool_quote_token_reserves: a.pool_quote_token_account.amount,
            base_amount_out: base_amount,
            quote_amount_out: quote_amount,
            lp_mint_supply: old_supply,
            pool: a.pool.key(),
            user: a.user.key(),
            user_base_token_account: a.user_base_token_account.key(),
            user_quote_token_account: a.user_quote_token_account.key(),
            user_pool_token_account: a.user_pool_token_account.key(),
            quote_transfer_fee,
        };
        emit!(event.clone());
        emit_cpi!(event);
    }
    Ok(())
}

fn quote_transfer_fee(mint: &AccountInfo, amount: u64, inverse: bool) -> Result<u64> {
    use anchor_spl::token_2022::spl_token_2022::{extension::{BaseStateWithExtensions, StateWithExtensions, transfer_fee::TransferFeeConfig}, state::Mint as SplMint};
    if mint.owner == &anchor_spl::token::ID { return Ok(0); }
    let data = mint.try_borrow_data()?;
    let mint = StateWithExtensions::<SplMint>::unpack(&data)?;
    if let Ok(fees) = mint.get_extension::<TransferFeeConfig>() {
        let epoch = Clock::get()?.epoch;
        let fee = if inverse { fees.calculate_inverse_epoch_fee(epoch, amount) } else { fees.calculate_epoch_fee(epoch, amount) };
        fee.ok_or_else(|| error!(PumpAmmError::Overflow))
    } else { Ok(0) }
}
