//! Partial independently compiled Mayhem implementation: 24 recovered administration, sweep,
//! burn and recovered trade handlers. Unknown fields are preserved as byte arrays, not guessed names.
//! This is not a complete or byte-identical program reconstruction.
use anchor_lang::prelude::*;
mod checked_program;
use checked_program::{CheckedSystemProgram, CheckedSystemProgramBumps, __client_accounts_checked_system_program, __cpi_client_accounts_checked_system_program};
use anchor_spl::{associated_token::AssociatedToken, token_interface::{Mint, TokenAccount, TokenInterface}};

pub mod state;
pub mod instructions;
pub use instructions::burn::*;
pub use instructions::sell::*;
pub use instructions::buy::*;
pub use instructions::sell_v2::*;
pub use instructions::buy_v2::*;
pub use instructions::buy_pump_swap::*;
pub use instructions::sell_pump_swap::*;

declare_id!("MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e");

#[program]
pub mod mayhem_recovered {
    use super::*;
    pub fn buy_pump_swap(ctx: Context<BuyPumpSwap>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> { instructions::buy_pump_swap::handler(ctx, reference, tolerance_bps, retained_reserve_bps) }
    pub fn sell_pump_swap(ctx: Context<SellPumpSwap>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> { instructions::sell_pump_swap::handler(ctx, reference, tolerance_bps, retained_reserve_bps) }
    pub fn buy_v2(ctx: Context<BuyV2>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> { instructions::buy_v2::handler(ctx, reference, tolerance_bps, retained_reserve_bps) }
    pub fn sell_v2(ctx: Context<SellV2>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> { instructions::sell_v2::handler(ctx, reference, tolerance_bps, retained_reserve_bps) }
    pub fn buy(ctx: Context<LegacyBuy>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> { instructions::buy::handler(ctx, reference, tolerance_bps, retained_reserve_bps) }
    pub fn sell(ctx: Context<LegacySell>, reference: u128, tolerance_bps: u16, retained_reserve_bps: u16) -> Result<()> {
        instructions::sell::handler(ctx, reference, tolerance_bps, retained_reserve_bps)
    }
    pub fn burn_tokens(ctx: Context<BurnTokens>) -> Result<()> {
        instructions::burn::handler(ctx)
    }
    pub fn sweep_fees<'info>(ctx: Context<'info, SweepFees<'info>>) -> Result<()> {
        let limit = if ctx.accounts.quote_mint.key() == anchor_spl::token::spl_token::native_mint::ID { ctx.accounts.global_params.max_sol_per_sweep } else { ctx.accounts.global_params.max_stable_per_sweep };
        let amount = sweep_remaining(ctx.remaining_accounts, &ctx.accounts.trader.to_account_info(), &ctx.accounts.trader_quote_ata.to_account_info(), &ctx.accounts.token_program.to_account_info(), ctx.accounts.quote_mint.key(), limit, false)?;
        let event = SweepEvent { amount, timestamp: Clock::get()?.unix_timestamp }; emit!(event); emit_cpi!(event); Ok(())
    }
    pub fn sweep_fees_admin<'info>(ctx: Context<'info, SweepFeesAdmin<'info>>) -> Result<()> {
        let amount = sweep_remaining(ctx.remaining_accounts, &ctx.accounts.admin.to_account_info(), &ctx.accounts.admin_quote_ata.to_account_info(), &ctx.accounts.token_program.to_account_info(), ctx.accounts.quote_mint.key(), u64::MAX, true)?;
        let event = SweepEvent { amount, timestamp: Clock::get()?.unix_timestamp }; emit!(event); emit_cpi!(event); Ok(())
    }
    pub fn withdraw_quote_admin(ctx: Context<WithdrawQuoteAdmin>, amount: u64) -> Result<()> {
        let now = Clock::get()?.unix_timestamp;
        let state = &mut ctx.accounts.global_params;
        let last = i64::from_le_bytes(state.reset_stable_suffix[16..24].try_into().unwrap());
        let interval = i64::from_le_bytes(state.reset_stable_suffix[8..16].try_into().unwrap());
        if last != 0 && interval != 0 { require_gte!(now, last + interval, MayhemError::WithdrawRateLimit); }
        state.reset_stable_suffix[16..24].copy_from_slice(&now.to_le_bytes());
        let bump = [ctx.bumps.sol_vault];
        let seeds: &[&[u8]] = &[b"sol-vault", &bump];
        anchor_spl::token::transfer(CpiContext::new_with_signer(
            ctx.accounts.token_program.key(), anchor_spl::token::Transfer {
                from: ctx.accounts.vault_quote_ata.to_account_info(),
                to: ctx.accounts.admin_quote_ata.to_account_info(),
                authority: ctx.accounts.sol_vault.to_account_info(),
            }, &[seeds]), amount)
    }
    pub fn withdraw_admin(ctx: Context<WithdrawAdmin>, amount: u64) -> Result<()> {
        let now = Clock::get()?.unix_timestamp;
        let state = &mut ctx.accounts.global_params;
        let last = i64::from_le_bytes(state.reset_middle[1..9].try_into().unwrap());
        let interval = i64::from_le_bytes(state.reset_middle[17..25].try_into().unwrap());
        if last != 0 && interval != 0 {
            // The captured original panics on signed-add overflow here.
            require_gte!(now, last + interval, MayhemError::WithdrawRateLimit);
        }
        state.reset_middle[1..9].copy_from_slice(&now.to_le_bytes());
        let bump = [ctx.bumps.sol_vault];
        let seeds: &[&[u8]] = &[b"sol-vault", &bump];
        anchor_lang::system_program::transfer(
            CpiContext::new_with_signer(ctx.accounts.system_program.key(),
                anchor_lang::system_program::Transfer {
                    from: ctx.accounts.sol_vault.to_account_info(),
                    to: ctx.accounts.admin.to_account_info(),
                }, &[seeds]), amount)
    }
    pub fn extend_account(ctx: Context<ExtendAccount>) -> Result<()> {
        let account = ctx.accounts.account.to_account_info();
        let old_size = account.data_len();
        let new_size = {
            let data = account.try_borrow_data()?;
            match data.get(..8) {
                Some(d) if d == GlobalParams::DISCRIMINATOR => 318,
                Some(d) if d == FeeRecipient::DISCRIMINATOR => 74,
                Some(d) if d == [0xb1,0xfd,0xbf,0x7d,0xcb,0x16,0x86,0x6b] => 170,
                _ => return err!(MayhemError::AccountTypeNotSupported),
            }
        };
        if old_size == new_size {
            msg!("Account already has the correct size");
            return Ok(());
        }
        if old_size > new_size {
            msg!("Account already has more than {} bytes: {}", new_size, old_size);
            return Ok(());
        }
        let required = Rent::get()?.minimum_balance(new_size).saturating_sub(account.lamports());
        if required > 0 {
            anchor_lang::system_program::transfer(
                CpiContext::new(ctx.accounts.system_program.key(),
                    anchor_lang::system_program::Transfer {
                        from: ctx.accounts.user.to_account_info(), to: account.clone()
                    }), required)?;
        }
        account.resize(new_size)?;
        let event = ExtendAccountEvent {
            account: account.key(), user: ctx.accounts.user.key(),
            old_size: old_size as u64, new_size: new_size as u64,
            timestamp: Clock::get()?.unix_timestamp,
        };
        emit!(event);
        emit_cpi!(event);
        Ok(())
    }
    pub fn initialize_fee_recipient(ctx: Context<InitializeFeeRecipient>, index: u8) -> Result<()> {
        require!(index < 8, MayhemError::MaxFeeRecipientsExceeded);
        ctx.accounts.fee_recipient.bump = ctx.bumps.fee_recipient;
        ctx.accounts.fee_recipient.index = index;
        Ok(())
    }
    pub fn initialize_global_params(ctx: Context<InitializeGlobalParams>) -> Result<()> {
        ctx.accounts.global_params.admin = ctx.accounts.admin.key();
        Ok(())
    }
    pub fn update_global_params(ctx: Context<Admin>, args: UpdateGlobalParamsArgs) -> Result<()> {
        let state = &mut ctx.accounts.global_params;
        if let Some(v) = args.field_0 { state.reset_prefix[0..4].copy_from_slice(&v.to_le_bytes()); }
        if let Some(v) = args.field_1 { state.reset_prefix[4..8].copy_from_slice(&v.to_le_bytes()); }
        for (value, offset) in [(args.field_2, 8), (args.field_3, 16), (args.field_4, 24), (args.field_5, 32)] {
            if let Some(v) = value { state.reset_prefix[offset..offset+8].copy_from_slice(&v.to_le_bytes()); }
        }
        if let Some(v) = args.field_6 { state.reset_middle[0] = v; }
        if let Some(v) = args.field_7 { state.reset_middle[9..17].copy_from_slice(&v.to_le_bytes()); }
        if let Some(v) = args.field_8 { state.reset_middle[17..25].copy_from_slice(&v.to_le_bytes()); }
        if let Some(v) = args.field_9 { state.preserved_middle_a.copy_from_slice(&v.to_le_bytes()); }
        if let Some(v) = args.field_10 { state.field_10 = v; }
        for (value, offset) in [(args.field_11, 0), (args.field_12, 8), (args.field_13, 16)] {
            if let Some(v) = value { state.reset_stable_prefix[offset..offset+8].copy_from_slice(&v.to_le_bytes()); }
        }
        if let Some(v) = args.field_14 { state.reset_stable_suffix[0..8].copy_from_slice(&v.to_le_bytes()); }
        if let Some(v) = args.field_15 { state.reset_stable_suffix[8..16].copy_from_slice(&v.to_le_bytes()); }
        let old_version = state.version;
        state.version = state.version.checked_add(1).ok_or(MayhemError::MathOverflow)?;
        let event = GlobalParamsUpdateEvent {
            old_version, new_version: state.version,
            field_0: u32::from_le_bytes(state.reset_prefix[0..4].try_into().unwrap()),
            field_1: u32::from_le_bytes(state.reset_prefix[4..8].try_into().unwrap()),
            field_2: u64::from_le_bytes(state.reset_prefix[8..16].try_into().unwrap()),
            field_3: u64::from_le_bytes(state.reset_prefix[16..24].try_into().unwrap()),
            field_4: u64::from_le_bytes(state.reset_prefix[24..32].try_into().unwrap()),
            field_5: u64::from_le_bytes(state.reset_prefix[32..40].try_into().unwrap()),
            field_6: state.reset_middle[0],
            field_7: u64::from_le_bytes(state.reset_middle[9..17].try_into().unwrap()),
            field_8: u64::from_le_bytes(state.reset_middle[17..25].try_into().unwrap()),
            field_9: u64::from_le_bytes(state.preserved_middle_a),
            field_10: state.field_10,
            field_11: u64::from_le_bytes(state.reset_stable_prefix[0..8].try_into().unwrap()),
            field_12: u64::from_le_bytes(state.reset_stable_prefix[8..16].try_into().unwrap()),
            field_13: u64::from_le_bytes(state.reset_stable_prefix[16..24].try_into().unwrap()),
            field_14: u64::from_le_bytes(state.reset_stable_suffix[0..8].try_into().unwrap()),
            field_15: u64::from_le_bytes(state.reset_stable_suffix[8..16].try_into().unwrap()),
        };
        emit!(event);
        emit_cpi!(event);
        Ok(())
    }
    pub fn update_admin(ctx: Context<Admin>, new_admin: Pubkey) -> Result<()> {
        ctx.accounts.global_params.admin = new_admin;
        Ok(())
    }
    pub fn update_trader(ctx: Context<Admin>, new_trader: Pubkey) -> Result<()> {
        ctx.accounts.global_params.trader = new_trader;
        Ok(())
    }
    pub fn update_max_sol_per_sweep(ctx: Context<Admin>, value: u64) -> Result<()> {
        ctx.accounts.global_params.max_sol_per_sweep = value;
        Ok(())
    }
    pub fn update_max_stable_per_sweep(ctx: Context<Admin>, value: u64) -> Result<()> {
        ctx.accounts.global_params.max_stable_per_sweep = value;
        Ok(())
    }
    pub fn reset_sol_deployed(ctx: Context<Admin>) -> Result<()> {
        ctx.accounts.global_params.sol_deployed = 0;
        Ok(())
    }
    pub fn reset_stable_deployed(ctx: Context<Admin>) -> Result<()> {
        ctx.accounts.global_params.stable_deployed = 0;
        Ok(())
    }
    pub fn reset_state(ctx: Context<Admin>) -> Result<()> {
        let state = &mut ctx.accounts.global_params;
        state.reset_prefix = [0; 40];
        state.paused = false;
        state.sol_deployed = 0;
        state.reset_middle = [0; 25];
        state.reset_stable_prefix = [0; 24];
        state.stable_deployed = 0;
        state.reset_stable_suffix = [0; 24];
        Ok(())
    }
    pub fn stop_trading(ctx: Context<Admin>) -> Result<()> {
        require_eq!(ctx.accounts.global_params.paused, false, MayhemError::TradingPaused);
        ctx.accounts.global_params.paused = true;
        Ok(())
    }
    pub fn resume_trading(ctx: Context<Admin>) -> Result<()> {
        // The original also uses 6000/TradingPaused when already active.
        require_eq!(ctx.accounts.global_params.paused, true, MayhemError::TradingPaused);
        ctx.accounts.global_params.paused = false;
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Admin<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(mut, seeds = [b"global-params"], bump, has_one = admin)]
    pub global_params: Account<'info, GlobalParams>,
    pub system_program: CheckedSystemProgram<'info>,
    /// CHECK: Preserve the captured runtime PDA derivation and ConstraintSeeds error.
    #[account(seeds = [b"__event_authority"], bump)]
    pub event_authority: UncheckedAccount<'info>,
    /// CHECK: Captured parser consumes this account without an address constraint.
    pub program: UncheckedAccount<'info>,
}

/// Exact observed Borsh positions; opaque bytes remain named by behavior.
/// This is not an assertion of historical field names or Rust memory layout.
#[account]
pub struct GlobalParams {
    pub reset_prefix: [u8; 40], // serialized offset 8
    pub paused: bool, // 48
    pub admin: Pubkey, // 49
    pub trader: Pubkey, // 81
    pub sol_deployed: i128, // 113
    pub preserved_middle_a: [u8; 8], // 129
    pub reset_middle: [u8; 25], // 137
    pub version: u32, // 162, incremented by update_global_params
    pub field_10: u64, // 166
    pub max_sol_per_sweep: u64, // 174
    pub reset_stable_prefix: [u8; 24], // 182
    pub stable_deployed: i128, // 206
    pub reset_stable_suffix: [u8; 24], // 222
    pub max_stable_per_sweep: u64, // 246
}

#[error_code]
pub enum MayhemError {
    #[msg("Trading is paused")]
    TradingPaused,
    #[msg("Trading is active")]
    TradingActive,
    #[msg("Math overflow")]
    MathOverflow,
    #[msg("Withdraw Rate limit")]
    WithdrawRateLimit = 14,
    #[msg("Account type not supported")]
    AccountTypeNotSupported = 16,
    #[msg("Only 8 fee recipients supported")]
    MaxFeeRecipientsExceeded = 17,
}

/// Recovered serialized widths/order. Semantic names remain unresolved.
#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct UpdateGlobalParamsArgs {
    pub field_0: Option<u32>,
    pub field_1: Option<u32>,
    pub field_2: Option<u64>,
    pub field_3: Option<u64>,
    pub field_4: Option<u64>,
    pub field_5: Option<u64>,
    pub field_6: Option<u8>,
    pub field_7: Option<u64>,
    pub field_8: Option<u64>,
    pub field_9: Option<u64>,
    pub field_10: Option<u64>,
    pub field_11: Option<u64>,
    pub field_12: Option<u64>,
    pub field_13: Option<u64>,
    pub field_14: Option<u64>,
    pub field_15: Option<u64>,
}

// The discriminator is observed from original emitted data. Historical event
// type name remains unresolved; overriding it avoids pretending to know it.
#[event(discriminator = [0x63,0xa7,0x5c,0x98,0x98,0xe3,0x26,0x29])]
pub struct GlobalParamsUpdateEvent {
    pub old_version: u32,
    pub new_version: u32,
    pub field_0: u32,
    pub field_1: u32,
    pub field_2: u64,
    pub field_3: u64,
    pub field_4: u64,
    pub field_5: u64,
    pub field_6: u8,
    pub field_7: u64,
    pub field_8: u64,
    pub field_9: u64,
    pub field_10: u64,
    pub field_11: u64,
    pub field_12: u64,
    pub field_13: u64,
    pub field_14: u64,
    pub field_15: u64,
}

#[derive(Accounts)]
pub struct InitializeGlobalParams<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(init, payer = admin, space = 254, seeds = [b"global-params"], bump)]
    pub global_params: Account<'info, GlobalParams>,
    pub system_program: CheckedSystemProgram<'info>,
}

#[account]
pub struct FeeRecipient {
    pub bump: u8,
    pub index: u8,
    pub opaque: [u8; 32],
}

#[derive(Accounts)]
#[instruction(index: u8)]
pub struct InitializeFeeRecipient<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(address = anchor_spl::token::spl_token::native_mint::ID)]
    pub wsol_mint: InterfaceAccount<'info, Mint>,
    #[account(init, payer = admin, space = 42, seeds = [b"fee-recipient".as_ref(), &[index]], bump)]
    pub fee_recipient: Account<'info, FeeRecipient>,
    #[account(init, payer = admin, associated_token::mint = wsol_mint, associated_token::authority = fee_recipient, associated_token::token_program = token_program)]
    pub fee_recipient_ata: InterfaceAccount<'info, TokenAccount>,
    #[account(mut, seeds = [b"global-params"], bump)]
    pub global_params: Account<'info, GlobalParams>,
    pub system_program: CheckedSystemProgram<'info>,
    #[account(address = anchor_spl::token::ID)]
    pub token_program: Interface<'info, TokenInterface>,
    pub associated_token_program: Program<'info, AssociatedToken>,
}

#[derive(Accounts)]
pub struct ExtendAccount<'info> {
    /// CHECK: Owner/mut checked here; recognized discriminator checked in handler.
    #[account(mut, owner = ID)]
    pub account: UncheckedAccount<'info>,
    pub user: Signer<'info>,
    pub system_program: CheckedSystemProgram<'info>,
    /// CHECK: Preserve the captured runtime PDA derivation and ConstraintSeeds error.
    #[account(seeds = [b"__event_authority"], bump)]
    pub event_authority: UncheckedAccount<'info>,
    /// CHECK: Captured parser consumes this account without an address constraint.
    pub program: UncheckedAccount<'info>,
}

#[event(discriminator = [0x61,0x61,0xd7,0x90,0x5d,0x92,0x16,0x7c])]
pub struct ExtendAccountEvent {
    pub account: Pubkey,
    pub user: Pubkey,
    pub old_size: u64,
    pub new_size: u64,
    pub timestamp: i64,
}

#[derive(Accounts)]
pub struct WithdrawAdmin<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(mut, seeds = [b"global-params"], bump, has_one = admin)]
    pub global_params: Account<'info, GlobalParams>,
    /// CHECK: PDA/writability enforced here; System CPI enforces spending owner.
    #[account(mut, seeds = [b"sol-vault"], bump)]
    pub sol_vault: UncheckedAccount<'info>,
    pub system_program: CheckedSystemProgram<'info>,
}

#[derive(Accounts)]
pub struct WithdrawQuoteAdmin<'info> {
    #[account(mut)] pub admin: Signer<'info>,
    #[account(mut, seeds = [b"global-params"], bump, has_one = admin)]
    pub global_params: Account<'info, GlobalParams>,
    /// CHECK: PDA authorizes its token accounts.
    #[account(mut, seeds = [b"sol-vault"], bump)] pub sol_vault: UncheckedAccount<'info>,
    pub quote_mint: InterfaceAccount<'info, Mint>,
    #[account(mut, associated_token::mint = quote_mint, associated_token::authority = sol_vault, associated_token::token_program = token_program)]
    pub vault_quote_ata: InterfaceAccount<'info, TokenAccount>,
    #[account(init_if_needed, payer = admin, associated_token::mint = quote_mint, associated_token::authority = admin, associated_token::token_program = token_program)]
    pub admin_quote_ata: InterfaceAccount<'info, TokenAccount>,
    pub token_program: Interface<'info, TokenInterface>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    pub system_program: CheckedSystemProgram<'info>,
}

#[event(discriminator = [218,130,134,253,101,109,149,152])]
pub struct SweepEvent { pub amount: u64, pub timestamp: i64 }
fn sweep_remaining<'info>(remaining: &'info [AccountInfo<'info>], destination: &AccountInfo<'info>, destination_ata: &AccountInfo<'info>, token: &AccountInfo<'info>, mint: Pubkey, limit: u64, admin: bool) -> Result<u64> {
    require_eq!(remaining.len(),16,MayhemError::AccountTypeNotSupported);
    let rent = Rent::get()?;
    let mut total = 0u64;
    for pair in remaining.chunks_exact(2) {
        let mut recipient=Account::<FeeRecipient>::try_from(&pair[0])?;
        let ata=InterfaceAccount::<TokenAccount>::try_from(&pair[1])?;
        let before_total=total;
        let available = limit - total;
        let token_amount = ata.amount.min(available);
        if token_amount > 0 {
            let index=[recipient.index];let bump=[recipient.bump];let seeds: &[&[u8]]=&[b"fee-recipient", &index, &bump];
            anchor_spl::token::transfer(CpiContext::new_with_signer(*token.key, anchor_spl::token::Transfer { from: ata.to_account_info(), to: destination_ata.clone(), authority: recipient.to_account_info() }, &[seeds]),token_amount)?;
            total += token_amount;
        }
        if mint == anchor_spl::token::spl_token::native_mint::ID {
            let account = recipient.to_account_info();
            let amount = (account.lamports() - rent.minimum_balance(account.data_len())).min(limit-total);
            **account.try_borrow_mut_lamports()? -= amount;
            **destination.try_borrow_mut_lamports()? += amount;
            total += amount;
        }
        let (counter, timestamp) = if mint == anchor_spl::token::spl_token::native_mint::ID { (8, 0) } else { (16, 24) };
        let previous=u64::from_le_bytes(recipient.opaque[counter..counter+8].try_into().unwrap());
        recipient.opaque[counter..counter+8].copy_from_slice(&(previous + total-before_total).to_le_bytes());
        if !admin { recipient.opaque[timestamp..timestamp+8].copy_from_slice(&Clock::get()?.unix_timestamp.to_le_bytes()); }
        recipient.exit(&ID)?;
    }
    Ok(total)
}

#[derive(Accounts)]
pub struct SweepFees<'info> {
    #[account(mut)] pub trader: Signer<'info>,
    #[account(mut, seeds=[b"global-params"], bump, has_one=trader)] pub global_params: Account<'info, GlobalParams>,
    pub quote_mint: InterfaceAccount<'info, Mint>,
    #[account(mut, associated_token::mint=quote_mint, associated_token::authority=trader, associated_token::token_program=token_program)] pub trader_quote_ata: InterfaceAccount<'info, TokenAccount>,
    pub system_program: CheckedSystemProgram<'info>,
    #[account(address=anchor_spl::token::ID)] pub token_program: Interface<'info,TokenInterface>,
    pub associated_token_program: Program<'info,AssociatedToken>,
    /// CHECK: Preserve the captured runtime PDA derivation and ConstraintSeeds error.
    #[account(seeds = [b"__event_authority"], bump)]
    pub event_authority: UncheckedAccount<'info>,
    /// CHECK: Captured parser consumes this account without an address constraint.
    pub program: UncheckedAccount<'info>,
}

#[derive(Accounts)]
pub struct SweepFeesAdmin<'info> {
    #[account(mut)] pub admin: Signer<'info>,
    #[account(mut, seeds=[b"global-params"], bump, has_one=admin)] pub global_params: Account<'info, GlobalParams>,
    pub quote_mint: InterfaceAccount<'info, Mint>,
    #[account(mut, associated_token::mint=quote_mint, associated_token::authority=admin, associated_token::token_program=token_program)] pub admin_quote_ata: InterfaceAccount<'info, TokenAccount>,
    pub system_program: CheckedSystemProgram<'info>,
    #[account(address=anchor_spl::token::ID)] pub token_program: Interface<'info,TokenInterface>,
    pub associated_token_program: Program<'info,AssociatedToken>,
    /// CHECK: Preserve the captured runtime PDA derivation and ConstraintSeeds error.
    #[account(seeds = [b"__event_authority"], bump)]
    pub event_authority: UncheckedAccount<'info>,
    /// CHECK: Captured parser consumes this account without an address constraint.
    pub program: UncheckedAccount<'info>,
}
