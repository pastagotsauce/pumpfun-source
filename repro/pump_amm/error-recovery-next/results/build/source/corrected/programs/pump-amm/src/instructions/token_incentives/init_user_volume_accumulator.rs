use crate::*;

#[event_cpi]
#[derive(Accounts)]
pub struct InitUserVolumeAccumulator<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,
    /// CHECK: A user key is sufficient; the user need not sign initialization.
    pub user: AccountInfo<'info>,
    #[account(init_if_needed, payer = payer, space = 137, seeds = [b"user_volume_accumulator", user.key().as_ref()], bump)]
    pub user_volume_accumulator: Account<'info, UserVolumeAccumulator>,
    pub system_program: Program<'info, System>,
}
