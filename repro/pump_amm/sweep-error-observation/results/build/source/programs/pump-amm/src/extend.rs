use crate::*;
#[event_cpi]
#[derive(Accounts)]
pub struct ExtendAccount<'info> {
    /// CHECK: this instruction handles raw supported account discriminators.
    #[account(mut,owner=crate::ID)]
    pub account: UncheckedAccount<'info>,
    #[account(mut)]
    pub user: Signer<'info>,
    pub system_program: Program<'info, System>,
}
pub fn execute(ctx: Context<ExtendAccount>) -> Result<()> {
    let info = ctx.accounts.account.to_account_info();
    let current = info.data_len();
    let size = {
        let data = info.try_borrow_data()?;
        match data.get(..8) {
            Some(d) if d == Pool::DISCRIMINATOR => 301,
            Some(d) if d == GlobalConfig::DISCRIMINATOR => 949,
            Some(d) if d == UserVolumeAccumulator::DISCRIMINATOR => 137,
            Some(d) if d == [202, 42, 246, 43, 142, 190, 30, 255] => 600,
            _ => return err!(PumpAmmError::AccountTypeNotSupported),
        }
    };
    if current >= size {
        return Ok(());
    }
    let rent = Rent::get()?;
    let delta = rent
        .minimum_balance(size)
        .checked_sub(rent.minimum_balance(current))
        .ok_or(PumpAmmError::Overflow)?;
    anchor_lang::system_program::transfer(
        CpiContext::new(
            ctx.accounts.system_program.to_account_info(),
            anchor_lang::system_program::Transfer {
                from: ctx.accounts.user.to_account_info(),
                to: info.clone(),
            },
        ),
        delta,
    )?;
    info.realloc(size, false)?;
    let event = ExtendAccountEvent {
        timestamp: Clock::get()?.unix_timestamp,
        account: info.key(),
        user: ctx.accounts.user.key(),
        current_size: current as u64,
        new_size: size as u64,
    };
    emit!(event.clone());
    emit_cpi!(event);
    Ok(())
}
#[event]
#[derive(Clone)]
pub struct ExtendAccountEvent {
    pub timestamp: i64,
    pub account: Pubkey,
    pub user: Pubkey,
    pub current_size: u64,
    pub new_size: u64,
}
