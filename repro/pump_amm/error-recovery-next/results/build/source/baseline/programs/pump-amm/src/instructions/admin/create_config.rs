//! Static-only reconstruction; fixed-admin positive execution is unvalidated.
use crate::*;

const FIXED_ADMIN: Pubkey = anchor_lang::solana_program::pubkey!("8LWu7QM2dGR1G8nKDHthckea57bkCzXyBTAKPJUBDHo8");

#[event_cpi]
#[derive(Accounts)]
pub struct CreateConfig<'info> {
    #[account(mut, address = FIXED_ADMIN @ PumpAmmError::InvalidAdmin)]
    pub admin: Signer<'info>,
    #[account(init, payer = admin, space = 949, seeds = [b"global_config"], bump)]
    pub global_config: Account<'info, GlobalConfig>,
    pub system_program: Program<'info, System>,
}

#[event]
#[derive(Clone)]
pub struct CreateConfigEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub lp_fee_basis_points: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee_recipients: [Pubkey; 8],
    pub coin_creator_fee_basis_points: u64,
    pub admin_set_coin_creator_authority: Pubkey,
}
