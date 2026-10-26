use super::*;
use anchor_spl::token_interface::TokenInterface;
use anchor_lang::Discriminator;

#[event]
#[derive(Clone)]
pub struct BuyEvent {
    pub timestamp: i64,
    pub base_amount_out: u64,
    pub max_quote_amount_in: u64,
    pub user_base_token_reserves: u64,
    pub user_quote_token_reserves: u64,
    pub pool_base_token_reserves: u64,
    pub pool_quote_token_reserves: u64,
    pub quote_amount_in: u64,
    pub lp_fee_basis_points: u64,
    pub lp_fee: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee: u64,
    pub quote_amount_in_with_lp_fee: u64,
    pub user_quote_amount_in: u64,
    pub pool: Pubkey,
    pub user: Pubkey,
    pub user_base_token_account: Pubkey,
    pub user_quote_token_account: Pubkey,
    pub protocol_fee_recipient: Pubkey,
    pub protocol_fee_recipient_token_account: Pubkey,
    pub coin_creator: Pubkey,
    pub coin_creator_fee_basis_points: u64,
    pub coin_creator_fee: u64,
    pub track_volume: bool,
    pub total_unclaimed_tokens: u64,
    pub total_claimed_tokens: u64,
    pub current_sol_volume: u64,
    pub last_update_timestamp: i64,
    pub min_base_amount_out: u64,
    pub ix_name: String,
    pub cashback_fee_basis_points: u64,
    pub cashback: u64,
    pub buyback_fee_basis_points: u64,
    pub buyback_fee: u64,
    pub virtual_quote_reserves: i128,
    pub can_boost: bool,
    pub base_supply: u64,
    pub holder_rewards_bps: u64,
    pub holder_rewards: u64,
    pub creator_fee_unclaimed: u64,
    pub quote_transfer_fee: u64,
}

#[event]
#[derive(Clone)]
pub struct SellEvent {
    pub timestamp: i64,
    pub base_amount_in: u64,
    pub min_quote_amount_out: u64,
    pub user_base_token_reserves: u64,
    pub user_quote_token_reserves: u64,
    pub pool_base_token_reserves: u64,
    pub pool_quote_token_reserves: u64,
    pub quote_amount_out: u64,
    pub lp_fee_basis_points: u64,
    pub lp_fee: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee: u64,
    pub quote_amount_out_without_lp_fee: u64,
    pub user_quote_amount_out: u64,
    pub pool: Pubkey,
    pub user: Pubkey,
    pub user_base_token_account: Pubkey,
    pub user_quote_token_account: Pubkey,
    pub protocol_fee_recipient: Pubkey,
    pub protocol_fee_recipient_token_account: Pubkey,
    pub coin_creator: Pubkey,
    pub coin_creator_fee_basis_points: u64,
    pub coin_creator_fee: u64,
    pub cashback_fee_basis_points: u64,
    pub cashback: u64,
    pub buyback_fee_basis_points: u64,
    pub buyback_fee: u64,
    pub virtual_quote_reserves: i128,
    pub can_boost: bool,
    pub base_supply: u64,
    pub holder_rewards_bps: u64,
    pub holder_rewards: u64,
    pub creator_fee_unclaimed: u64,
    pub quote_transfer_fee: u64,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct TradeFees { pub lp_fee_bps: u64, pub protocol_fee_bps: u64, pub creator_fee_bps: u64 }
#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct TradeFeeTier { pub market_cap_lamports_threshold: u128, pub fees: TradeFees }
#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct TradeFeeConfig { pub bump: u8, pub admin: Pubkey, pub flat_fees: TradeFees,
    pub fee_tiers: Vec<TradeFeeTier>, pub stable_fee_tiers: Vec<TradeFeeTier>, pub exotic_flat_fees: TradeFees }
pub const FEE_OWNER: Pubkey = anchor_lang::solana_program::pubkey!("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ");
pub const PUMP: Pubkey = anchor_lang::solana_program::pubkey!("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P");
impl Owner for TradeFeeConfig { fn owner() -> Pubkey { FEE_OWNER } }
impl Discriminator for TradeFeeConfig { const DISCRIMINATOR: &'static [u8] = &[143,52,146,187,219,123,76,155]; }
impl AccountSerialize for TradeFeeConfig {}
impl AccountDeserialize for TradeFeeConfig {
    fn try_deserialize(buf: &mut &[u8]) -> Result<Self> {
        require!(buf.len() >= 8, anchor_lang::error::ErrorCode::AccountDiscriminatorNotFound);
        require!(&buf[..8] == Self::DISCRIMINATOR, anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch);
        Self::try_deserialize_unchecked(buf)
    }
    fn try_deserialize_unchecked(buf: &mut &[u8]) -> Result<Self> {
        let mut result=Self::deserialize(&mut &buf[8..]).map_err(|_| error!(anchor_lang::error::ErrorCode::AccountDidNotDeserialize))?;
        if buf.len()<4073 {result.stable_fee_tiers.clear();}
        if buf.len()<4097 {result.exotic_flat_fees=TradeFees {lp_fee_bps:0,protocol_fee_bps:0,creator_fee_bps:0};}
        Ok(result)
    }
}
#[derive(Accounts)]
pub struct TradeV2<'info> {
    #[account(mut, has_one = base_mint @ PumpAmmError::InvalidBaseMint, has_one = quote_mint @ PumpAmmError::InvalidQuoteMint, has_one = pool_base_token_account @ PumpAmmError::InvalidPoolBaseTokenAccount, has_one = pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    #[account(mut)] pub user: Signer<'info>,
    pub global_config: Box<Account<'info, GlobalConfig>>,
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)] pub user_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)] pub user_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)] pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)] pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    pub base_token_program: Interface<'info, TokenInterface>,
    pub quote_token_program: Interface<'info, TokenInterface>,
    pub system_program: Program<'info, System>,
    #[account(init_if_needed, payer = user, space = 137, seeds = [b"user_volume_accumulator", user.key().as_ref()], bump)]
    pub user_volume_accumulator: Box<Account<'info, UserVolumeAccumulator>>,
    #[account(seeds = [b"fee_config", crate::ID.as_ref()], bump, seeds::program = FEE_OWNER)]
    pub fee_config: Box<Account<'info, TradeFeeConfig>>,
    /// CHECK: Token owner, mint and associated address are checked by the handler.
    #[account(mut)] pub buyback_fee_recipient: UncheckedAccount<'info>,
    /// CHECK: PDA signer for self events.
    #[account(seeds=[b"__event_authority"], bump)] pub event_authority: UncheckedAccount<'info>,
    pub program: Program<'info, PumpAmmProgram>,
}
pub struct PumpAmmProgram;
impl Id for PumpAmmProgram {fn id()->Pubkey {crate::ID}}
fn checked64(x: u128) -> Result<u64> { u64::try_from(x).map_err(|_| error!(PumpAmmError::Truncation)) }
fn fee(amount: u64, bps: u64) -> Result<u64> { checked64(((amount as u128)*(bps as u128)+9999)/10000) }
fn fees(a: &TradeV2, quote_reserve: u64) -> Result<TradeFees> {
    require!(a.fee_config.to_account_info().data_len() >= 2512, PumpAmmError::FeeConfigTooShort);
    let authority = Pubkey::find_program_address(&[b"pool-authority", a.base_mint.key().as_ref()], &PUMP).0;
    let mut selected = if a.pool.creator != authority { a.fee_config.flat_fees.clone() } else {
        let cap = (if a.pool.is_mayhem_mode {1_000_000_000_000_000u64} else {a.base_mint.supply} as u128).checked_mul(quote_reserve as u128).ok_or(PumpAmmError::Overflow)?.checked_div(a.pool_base_token_account.amount as u128).ok_or(PumpAmmError::DivisionByZero)?;
        let config = &a.fee_config;
        let quote = a.quote_mint.key();
        let other_normal=Pubkey::new_from_array([131,13,252,159,222,95,230,184,170,124,4,164,118,233,30,138,198,187,38,74,173,144,250,25,201,223,73,216,92,62,91,94]);
        if quote != Pubkey::default() && quote != anchor_spl::token::spl_token::native_mint::ID && quote != other_normal && quote != anchor_lang::solana_program::pubkey!("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") {
            if config.exotic_flat_fees.lp_fee_bps == 0 && config.exotic_flat_fees.protocol_fee_bps == 0 && config.exotic_flat_fees.creator_fee_bps == 0 {config.flat_fees.clone()} else {config.exotic_flat_fees.clone()}
        } else {
            let tiers = if quote == anchor_lang::solana_program::pubkey!("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") { &config.stable_fee_tiers } else { &config.fee_tiers };
            require!(!tiers.is_empty(), PumpAmmError::FeeTiersEmpty);
            if cap < tiers[0].market_cap_lamports_threshold { tiers[0].fees.clone() } else { tiers.iter().rev().find(|t| cap >= t.market_cap_lamports_threshold).unwrap_or(&tiers[0]).fees.clone() }
        }
    };
    if a.pool.creator_fee_bps != 0 { selected.creator_fee_bps = a.pool.creator_fee_bps; }
    Ok(selected)
}
pub fn execute(ctx: Context<TradeV2>, amount: u64, limit: u64, mode: u8) -> Result<()> {
    let a = &mut *ctx.accounts;
    require!(a.global_config.disable_flags & (if mode == 1 {16} else {8}) == 0, if mode == 1 {PumpAmmError::DisabledSell} else {PumpAmmError::DisabledBuy});
    prepare(a)?;
    let old_virtual = a.pool.virtual_quote_reserves;
    let old_accrued=a.pool.protocol_fees.checked_add(a.pool.creator_fees).ok_or(PumpAmmError::Overflow)?;
    let can_boost=old_virtual.checked_add(old_accrued as i128).ok_or(PumpAmmError::Overflow)? != 0;
    a.pool_quote_token_account.amount.checked_sub(old_accrued).ok_or(PumpAmmError::Overflow)?;
    let q = (a.pool_quote_token_account.amount as i128).checked_add(old_virtual).ok_or(PumpAmmError::Overflow)?;
    let q = u64::try_from(q).map_err(|_| error!(PumpAmmError::Overflow))?;
    let b = a.pool_base_token_account.amount;
    if mode == 0 {
        require!(amount > 0,PumpAmmError::ZeroBaseAmount); require!(limit > 0,PumpAmmError::ZeroQuoteAmount);
        require!(amount <= b,PumpAmmError::BuyMoreBaseAmountThanPoolReserves);
    }
    let selected = fees(a, q)?;
    let creator_bps = if a.pool.coin_creator == Pubkey::default() {0} else {selected.creator_fee_bps};
    let (base_amount, curve_quote, lp_fee, protocol_fee, creator_fee, total_quote) = if mode == 0 {
        require!(amount > 0, PumpAmmError::ZeroBaseAmount);
        require!(limit > 0, PumpAmmError::ZeroQuoteAmount);
        let denominator = b.checked_sub(amount).ok_or(PumpAmmError::BuyMoreBaseAmountThanPoolReserves)?;
        let quote = checked64((q as u128).checked_mul(amount as u128).ok_or(PumpAmmError::Overflow)?.checked_div(denominator as u128).ok_or(PumpAmmError::DivisionByZero)?)?.checked_add(1).ok_or(PumpAmmError::Overflow)?;
        let l = fee(quote,selected.lp_fee_bps)?; let p = fee(quote,selected.protocol_fee_bps)?; let c = fee(quote,creator_bps)?;
        let total = quote.checked_add(l).and_then(|v|v.checked_add(p)).and_then(|v|v.checked_add(c)).ok_or(PumpAmmError::Overflow)?;
        require!(total <= limit, PumpAmmError::ExceededSlippage);
        (amount,quote,l,p,c,total)
    } else if mode == 1 {
        require!(amount > 0, PumpAmmError::ZeroBaseAmount);
        let denominator = (b as u128) + (amount as u128);
        let quote = checked64((q as u128).checked_mul(amount as u128).ok_or(PumpAmmError::Overflow)?.checked_div(denominator as u128).ok_or(PumpAmmError::DivisionByZero)?)?;
        let l = fee(quote,selected.lp_fee_bps)?; let p = fee(quote,selected.protocol_fee_bps)?; let c = fee(quote,creator_bps)?;
        let total = quote.checked_sub(l).and_then(|v|v.checked_sub(p)).and_then(|v|v.checked_sub(c)).ok_or(PumpAmmError::Overflow)?;
        require!(total >= limit, PumpAmmError::ExceededSlippage);
        (amount,quote,l,p,c,total)
    } else {
        require!(limit > 0, PumpAmmError::ZeroBaseAmount); require!(amount > 0, PumpAmmError::ZeroQuoteAmount);
        let sum = checked64(selected.lp_fee_bps as u128 + selected.protocol_fee_bps as u128 + creator_bps as u128 + 10000)?;
        let available = amount.checked_sub(super::quote_transfer_fee(&a.quote_mint.to_account_info(), amount, false)?).ok_or(PumpAmmError::Overflow)?;
        let estimated = checked64((available as u128)*10000/(sum as u128))?;
        require!(estimated > 0, PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees);
        let l=fee(estimated,selected.lp_fee_bps)?;let p=fee(estimated,selected.protocol_fee_bps)?;let c=fee(estimated,creator_bps)?;
        estimated.checked_add(l).and_then(|v|v.checked_add(p)).and_then(|v|v.checked_add(c)).ok_or(PumpAmmError::Overflow)?;
        let quote=available.checked_sub(l).and_then(|v|v.checked_sub(p)).and_then(|v|v.checked_sub(c)).ok_or(PumpAmmError::BuyNotEnoughQuoteTokensToCoverFees)?;
        let quote=quote.min(estimated);
        let adjusted=quote.saturating_sub(1);
        let out=checked64((b as u128)*(adjusted as u128)/((q as u128)+(adjusted as u128)))?;
        require!(out >= limit, PumpAmmError::BuySlippageBelowMinBaseAmountOut);
        (out,quote,l,p,c,quote.checked_add(l).and_then(|v|v.checked_add(p)).and_then(|v|v.checked_add(c)).ok_or(PumpAmmError::Overflow)?)
    };
    let index=a.pool.index.to_le_bytes();let bump=[a.pool.pool_bump];let creator=a.pool.creator;let base=a.pool.base_mint;let quote=a.pool.quote_mint;
    let seeds:&[&[u8]]=&[b"pool",&index,creator.as_ref(),base.as_ref(),quote.as_ref(),&bump];
    if mode == 1 {
        let transfer_fee=super::quote_transfer_fee(&a.quote_mint.to_account_info(),total_quote,false)?;
        require!(total_quote.checked_sub(transfer_fee).ok_or(PumpAmmError::Overflow)? >= limit,PumpAmmError::ExceededSlippage);
        transfer(&a.base_token_program.to_account_info(),&a.base_mint,&a.user_base_token_account,&a.pool_base_token_account,&a.user.to_account_info(),&a.pool.to_account_info(),base_amount,true,seeds)?;
        transfer(&a.quote_token_program.to_account_info(),&a.quote_mint,&a.user_quote_token_account,&a.pool_quote_token_account,&a.user.to_account_info(),&a.pool.to_account_info(),total_quote,false,seeds)?;
    }
    let buyback_bps = if a.pool.is_mayhem_mode {0} else {a.global_config.buyback_basis_points};
    let buyback_fee=u64::try_from((protocol_fee as u128)*(buyback_bps as u128)/10000).expect("buyback fee fits u64");
    let buyback_received = buyback_fee.checked_sub(super::quote_transfer_fee(&a.quote_mint.to_account_info(), buyback_fee, false)?).ok_or(PumpAmmError::Overflow)?;
    let net_pool_quote = if mode == 1 { total_quote } else { total_quote.checked_sub(buyback_fee).ok_or(PumpAmmError::Overflow)? };
    let quote_transfer_fee = super::quote_transfer_fee(&a.quote_mint.to_account_info(), net_pool_quote, mode != 1)?;
    let pool_quote = if mode == 1 {net_pool_quote} else {net_pool_quote.checked_add(quote_transfer_fee).ok_or(PumpAmmError::Overflow)?};
    if mode == 0 { require!(pool_quote.checked_add(buyback_fee).ok_or(PumpAmmError::Overflow)? <= limit, PumpAmmError::ExceededSlippage); }
    if mode == 1 { require!(total_quote.checked_sub(quote_transfer_fee).ok_or(PumpAmmError::Overflow)? >= limit, PumpAmmError::ExceededSlippage); }
    let protocol_accrual = protocol_fee.checked_sub(buyback_fee).expect("buyback_fee never exceeds protocol_fee");
    let accrued = protocol_accrual.checked_add(creator_fee).ok_or(PumpAmmError::Overflow)?;

    if mode != 1 { transfer(&a.base_token_program.to_account_info(),&a.base_mint,&a.user_base_token_account,&a.pool_base_token_account,&a.user.to_account_info(),&a.pool.to_account_info(),base_amount,false,seeds)?; }
    if mode != 1 { transfer(&a.quote_token_program.to_account_info(),&a.quote_mint,&a.user_quote_token_account,&a.pool_quote_token_account,&a.user.to_account_info(),&a.pool.to_account_info(),pool_quote,true,seeds)?; }
    if buyback_fee > 0 {
        let from = if mode == 1 {a.pool_quote_token_account.to_account_info()} else {a.user_quote_token_account.to_account_info()};
        let authority=if mode == 1 {a.pool.to_account_info()} else {a.user.to_account_info()};
        let signer=[seeds];
        token_interface::transfer_checked(CpiContext::new_with_signer(a.quote_token_program.to_account_info(), token_interface::TransferChecked {from,to:a.buyback_fee_recipient.to_account_info(),mint:a.quote_mint.to_account_info(),authority},if mode==1 {&signer} else {&[]}),buyback_fee,a.quote_mint.decimals)?;
    }
    a.pool.protocol_fees=a.pool.protocol_fees.checked_add(protocol_accrual).ok_or(PumpAmmError::Overflow)?;
    a.pool.creator_fees=a.pool.creator_fees.checked_add(creator_fee).ok_or(PumpAmmError::Overflow)?;
    a.pool.virtual_quote_reserves=old_virtual.checked_sub(accrued as i128).ok_or(PumpAmmError::Overflow)?;

    if mode != 1 {
        let event = BuyEvent {
            timestamp: Clock::get()?.unix_timestamp,
            base_amount_out: base_amount,
            max_quote_amount_in: if mode == 2 {amount} else {limit},
            user_base_token_reserves: a.user_base_token_account.amount,
            user_quote_token_reserves: a.user_quote_token_account.amount,
            pool_base_token_reserves: b,
            pool_quote_token_reserves: a.pool_quote_token_account.amount,
            quote_amount_in: if mode == 2 {amount} else {curve_quote},
            lp_fee_basis_points: selected.lp_fee_bps,
            lp_fee: lp_fee,
            protocol_fee_basis_points: selected.protocol_fee_bps,
            protocol_fee: protocol_fee,
            quote_amount_in_with_lp_fee: curve_quote+lp_fee,
            user_quote_amount_in: if mode == 2 {curve_quote} else {total_quote},
            pool: a.pool.key(),
            user: a.user.key(),
            user_base_token_account: a.user_base_token_account.key(),
            user_quote_token_account: a.user_quote_token_account.key(),
            protocol_fee_recipient: Pubkey::default(),
            protocol_fee_recipient_token_account: Pubkey::default(),
            coin_creator: a.pool.coin_creator,
            coin_creator_fee_basis_points: selected.creator_fee_bps,
            coin_creator_fee: creator_fee,
            track_volume: false,
            total_unclaimed_tokens: a.user_volume_accumulator.total_unclaimed_tokens,
            total_claimed_tokens: a.user_volume_accumulator.total_claimed_tokens,
            current_sol_volume: a.user_volume_accumulator.current_sol_volume,
            last_update_timestamp: a.user_volume_accumulator.last_update_timestamp,
            min_base_amount_out: if mode == 2 {limit} else {amount},
            ix_name: if mode == 2 {"buy_exact_quote_in_v2".to_string()} else {"buy_v2".to_string()},
            cashback_fee_basis_points: 0,
            cashback: 0,
            buyback_fee_basis_points: buyback_bps,
            buyback_fee: buyback_received,
            virtual_quote_reserves: old_virtual,
            can_boost: can_boost,
            base_supply: if a.pool.is_mayhem_mode {1_000_000_000_000_000} else {a.base_mint.supply},
            holder_rewards_bps: if a.pool.is_holder_reward { selected.creator_fee_bps } else { 0 },
            holder_rewards: if a.pool.is_holder_reward { creator_fee } else { 0 },
            creator_fee_unclaimed: a.pool.creator_fees,
            quote_transfer_fee,
        };
        emit!(event.clone()); emit_cpi!(event);
    } else {
        let event = SellEvent {
            timestamp: Clock::get()?.unix_timestamp,
            base_amount_in: base_amount,
            min_quote_amount_out: limit,
            user_base_token_reserves: a.user_base_token_account.amount,
            user_quote_token_reserves: a.user_quote_token_account.amount,
            pool_base_token_reserves: b,
            pool_quote_token_reserves: a.pool_quote_token_account.amount,
            quote_amount_out: curve_quote,
            lp_fee_basis_points: selected.lp_fee_bps,
            lp_fee: lp_fee,
            protocol_fee_basis_points: selected.protocol_fee_bps,
            protocol_fee: protocol_fee,
            quote_amount_out_without_lp_fee: curve_quote-lp_fee,
            user_quote_amount_out: total_quote,
            pool: a.pool.key(),
            user: a.user.key(),
            user_base_token_account: a.user_base_token_account.key(),
            user_quote_token_account: a.user_quote_token_account.key(),
            protocol_fee_recipient: Pubkey::default(),
            protocol_fee_recipient_token_account: Pubkey::default(),
            coin_creator: a.pool.coin_creator,
            coin_creator_fee_basis_points: selected.creator_fee_bps,
            coin_creator_fee: creator_fee,
            cashback_fee_basis_points: 0,
            cashback: 0,
            buyback_fee_basis_points: buyback_bps,
            buyback_fee: buyback_received,
            virtual_quote_reserves: old_virtual,
            can_boost: can_boost,
            base_supply: if a.pool.is_mayhem_mode {1_000_000_000_000_000} else {a.base_mint.supply},
            holder_rewards_bps: if a.pool.is_holder_reward { selected.creator_fee_bps } else { 0 },
            holder_rewards: if a.pool.is_holder_reward { creator_fee } else { 0 },
            creator_fee_unclaimed: a.pool.creator_fees,
            quote_transfer_fee,
        };
        emit!(event.clone()); emit_cpi!(event);
    }
    Ok(())
}
fn transfer<'info>(program:&AccountInfo<'info>, mint:&InterfaceAccount<'info,Mint>, user:&InterfaceAccount<'info,TokenAccount>, vault:&InterfaceAccount<'info,TokenAccount>, user_authority:&AccountInfo<'info>, pool_authority:&AccountInfo<'info>,amount:u64,to_pool:bool,seeds:&[&[u8]]) -> Result<()> {
    if amount == 0 {return Ok(());}
    let authority=if to_pool {user_authority.clone()} else {pool_authority.clone()};
    if user.key()==vault.key(){require_keys_eq!(user.owner,authority.key(),PumpAmmError::SelfTransferNotAllowed);}
    let signer=[seeds];
    token_interface::transfer_checked(CpiContext::new_with_signer(program.clone(),token_interface::TransferChecked {
        from:if to_pool {user.to_account_info()} else {vault.to_account_info()},to:if to_pool {vault.to_account_info()} else {user.to_account_info()},mint:mint.to_account_info(),authority},if to_pool {&[]} else {&signer}),amount,mint.decimals)
}

#[inline(never)]
fn prepare(a:&mut TradeV2) -> Result<()> {
    let pool_info=a.pool.to_account_info();
    if pool_info.data_len()<287 {
        let needed=Rent::get()?.minimum_balance(287).saturating_sub(pool_info.lamports());
        if needed>0 {anchor_lang::system_program::transfer(CpiContext::new(a.system_program.to_account_info(),anchor_lang::system_program::Transfer {from:a.user.to_account_info(),to:pool_info.clone()}),needed)?;}
        pool_info.realloc(287,false)?;
    }
    require!(!a.pool.is_cashback_coin, PumpAmmError::CashbackCoinNotSupported);
    require_keys_eq!(*a.buyback_fee_recipient.to_account_info().owner,a.quote_token_program.key(),PumpAmmError::AccountTypeNotSupported);
    let buyback_info=a.buyback_fee_recipient.to_account_info();
    let buyback_token=TokenAccount::try_deserialize(&mut &buyback_info.try_borrow_data()?[..])?;
    require_keys_eq!(buyback_token.mint, a.quote_mint.key(), PumpAmmError::InvalidQuoteMint);
    require!(a.global_config.buyback_fee_recipients.contains(&buyback_token.owner), PumpAmmError::BuybackFeeRecipientNotAuthorized);
    let ata_program = anchor_lang::solana_program::pubkey!("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL");
    let recipient = Pubkey::find_program_address(&[buyback_token.owner.as_ref(),a.quote_token_program.key().as_ref(),a.quote_mint.key().as_ref()], &ata_program).0;
    require_keys_eq!(recipient, a.buyback_fee_recipient.key(), PumpAmmError::BuybackFeeRecipientNotAuthorized);
    if a.user_volume_accumulator.user == Pubkey::default() { a.user_volume_accumulator.user = a.user.key(); }
    Ok(())
}
