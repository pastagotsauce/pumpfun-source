use crate::*;
use anchor_spl::{
    associated_token::{self, AssociatedToken},
    token_interface::TokenInterface,
};
#[event_cpi]
#[derive(Accounts)]
pub struct SweepFees<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,
    pub global_config: Box<Account<'info, GlobalConfig>>,
    #[account(mut,has_one=quote_mint @ PumpAmmError::InvalidQuoteMint,has_one=pool_quote_token_account @ PumpAmmError::InvalidPoolQuoteTokenAccount)]
    pub pool: Box<Account<'info, Pool>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_token_program: Interface<'info, TokenInterface>,
    #[account(mut)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    /// CHECK: validated against configured recipients or creator vault PDA in handler.
    pub recipient: UncheckedAccount<'info>,
    /// CHECK: associated-token address constrained; token CPI validates initialized data.
    #[account(mut,seeds=[recipient.key().as_ref(),quote_token_program.key().as_ref(),quote_mint.key().as_ref()],bump,seeds::program=associated_token_program.key())]
    pub recipient_token_account: UncheckedAccount<'info>,
    pub system_program: Program<'info, System>,
    pub associated_token_program: Program<'info, AssociatedToken>,
}
pub fn execute(ctx: Context<SweepFees>, creator: bool) -> Result<()> {
    let a = &mut *ctx.accounts;
    require_keys_neq!(
        a.recipient.key(),
        Pubkey::default(),
        PumpAmmError::InvalidProtocolFeeRecipient
    );
    if creator {
        let expected = Pubkey::find_program_address(
            &[b"creator_vault", a.pool.coin_creator.as_ref()],
            &crate::ID,
        )
        .0;
        require_keys_eq!(
            a.recipient.key(),
            expected,
            anchor_lang::error::ErrorCode::ConstraintSeeds
        );
    } else {
        let key = a.recipient.key();
        let valid = if a.pool.is_mayhem_mode {
            a.global_config.reserved_fee_recipient == key
                || a.global_config.reserved_fee_recipients.contains(&key)
        } else {
            a.global_config
                .protocol_fee_recipients
                .binary_search(&key)
                .is_ok()
        };
        require!(valid, PumpAmmError::InvalidProtocolFeeRecipient);
    }
    let info = a.pool.to_account_info();
    if info.data_len() < 287 {
        let topup = Rent::get()?
            .minimum_balance(287)
            .saturating_sub(info.lamports());
        if topup > 0 {
            anchor_lang::system_program::transfer(
                CpiContext::new(
                    a.system_program.to_account_info(),
                    anchor_lang::system_program::Transfer {
                        from: a.payer.to_account_info(),
                        to: info.clone(),
                    },
                ),
                topup,
            )?;
        }
        info.realloc(287, false)?;
    }
    let amount = if creator {
        a.pool.creator_fees
    } else {
        a.pool.protocol_fees
    };
    let fees = a
        .pool
        .protocol_fees
        .checked_add(a.pool.creator_fees)
        .ok_or(PumpAmmError::Overflow)?;
    a.pool_quote_token_account
        .amount
        .checked_sub(fees)
        .ok_or(PumpAmmError::Overflow)?;
    if amount == 0 {
        msg!("Nothing to sweep for fee bucket {}", u8::from(creator));
        return Ok(());
    }
    let updated_virtual = a
        .pool
        .virtual_quote_reserves
        .checked_add(amount as i128)
        .ok_or(PumpAmmError::Overflow)?;
    if a.recipient_token_account.data_is_empty() {
        associated_token::create_idempotent(CpiContext::new(
            a.associated_token_program.to_account_info(),
            associated_token::Create {
                payer: a.payer.to_account_info(),
                associated_token: a.recipient_token_account.to_account_info(),
                authority: a.recipient.to_account_info(),
                mint: a.quote_mint.to_account_info(),
                system_program: a.system_program.to_account_info(),
                token_program: a.quote_token_program.to_account_info(),
            },
        ))?;
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
    if a.pool_quote_token_account.key() == a.recipient_token_account.key() {
        require!(
            a.pool_quote_token_account.owner == a.pool.key(),
            PumpAmmError::SelfTransferNotAllowed
        );
    }
    token_interface::transfer_checked(
        CpiContext::new_with_signer(
            a.quote_token_program.to_account_info(),
            token_interface::TransferChecked {
                from: a.pool_quote_token_account.to_account_info(),
                mint: a.quote_mint.to_account_info(),
                to: a.recipient_token_account.to_account_info(),
                authority: a.pool.to_account_info(),
            },
            &[seeds],
        ),
        amount,
        a.quote_mint.decimals,
    )?;
    a.pool.virtual_quote_reserves = updated_virtual;
    if creator {
        a.pool.creator_fees = 0
    } else {
        a.pool.protocol_fees = 0
    }
    let event = SweepPoolFeeEvent {
        timestamp: Clock::get()?.unix_timestamp,
        pool: a.pool.key(),
        base_mint: a.pool.base_mint,
        quote_mint: a.quote_mint.key(),
        recipient: a.recipient.key(),
        payer: a.payer.key(),
        amount,
        bucket: if creator { 1 } else { 0 },
    };
    emit!(event.clone());
    emit_cpi!(event);
    Ok(())
}
#[event]
#[derive(Clone)]
pub struct SweepPoolFeeEvent {
    pub timestamp: i64,
    pub pool: Pubkey,
    pub base_mint: Pubkey,
    pub quote_mint: Pubkey,
    pub recipient: Pubkey,
    pub payer: Pubkey,
    pub amount: u64,
    pub bucket: u8,
}
