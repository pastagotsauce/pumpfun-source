mod global_config;
use anchor_lang::Discriminator;
use anchor_lang::prelude::*;
#[event]
#[derive(Clone)]
pub struct DisableEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub disable_create_pool: bool,
    pub disable_deposit: bool,
    pub disable_withdraw: bool,
    pub disable_buy: bool,
    pub disable_sell: bool,
}
#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct GlobalConfig {
    pub admin: Pubkey,
    pub lp_fee_basis_points: u64,
    pub protocol_fee_basis_points: u64,
    pub disable_flags: u8,
    pub protocol_fee_recipients: [Pubkey; 8],
    pub coin_creator_fee_basis_points: u64,
    pub admin_set_coin_creator_authority: Pubkey,
    pub whitelist_pda: Pubkey,
    pub reserved_fee_recipient: Pubkey,
    pub mayhem_mode_enabled: bool,
    pub reserved_fee_recipients: [Pubkey; 7],
    pub is_cashback_enabled: bool,
    pub buyback_fee_recipients: [Pubkey; 8],
    pub buyback_basis_points: u64,
    pub boost_authority: Pubkey,
    pub boost_enabled: bool,
    pub creator_fee_configurable: bool,
    pub max_configurable_creator_fee_bps: u64,
}
#[event]
#[derive(Clone)]
pub struct UpdateAdminEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub new_admin: Pubkey,
}

impl Owner for GlobalConfig { fn owner() -> Pubkey { crate::ID } }
impl Discriminator for GlobalConfig { const DISCRIMINATOR: &'static [u8] = &[149, 8, 156, 202, 160, 252, 176, 217]; }
impl AccountDeserialize for GlobalConfig {
    fn try_deserialize(buf: &mut &[u8]) -> Result<Self> {
        if buf.len() < 8 || &buf[..8] != Self::DISCRIMINATOR {
            return Err(anchor_lang::solana_program::program_error::ProgramError::InvalidAccountData.into());
        }
        Self::try_deserialize_unchecked(buf)
    }
    fn try_deserialize_unchecked(buf: &mut &[u8]) -> Result<Self> {
        if buf.len() < 907 { return Err(anchor_lang::solana_program::program_error::ProgramError::InvalidAccountData.into()); }
        // Original selects legacy layouts at 907/940/949 total account bytes.
        let version_len = if buf.len() >= 949 { 949 } else if buf.len() >= 940 { 940 } else { 907 };
        let mut padded = [0u8; 949];
        padded[..version_len].copy_from_slice(&buf[..version_len]);
        Self::deserialize(&mut &padded[8..]).map_err(|err| anchor_lang::solana_program::program_error::ProgramError::BorshIoError(err.to_string()).into())
    }
}
impl AccountSerialize for GlobalConfig {
    fn try_serialize<W: std::io::Write>(&self, writer: &mut W) -> Result<()> {
        writer.write_all(Self::DISCRIMINATOR)?;
        self.serialize(writer)?;
        Ok(())
    }
}

#[event]
#[derive(Clone)]
pub struct UpdateFeeConfigEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub lp_fee_basis_points: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee_recipients: [Pubkey; 8],
    pub coin_creator_fee_basis_points: u64,
    pub admin_set_coin_creator_authority: Pubkey,
}

#[event]
#[derive(Clone)]
pub struct SetBoostAuthorityEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub old_boost_authority: Pubkey,
    pub new_boost_authority: Pubkey,
}

#[event]
#[derive(Clone)]
pub struct UpdateCreatorFeeConfigEvent {
    pub timestamp: i64,
    pub admin: Pubkey,
    pub creator_fee_configurable: bool,
    pub max_configurable_creator_fee_bps: u64,
}

#[event]
#[derive(Clone)]
pub struct ReservedFeeRecipientsEvent {
    pub timestamp: i64,
    pub reserved_fee_recipient: Pubkey,
    pub reserved_fee_recipients: [Pubkey; 7],
}

#[event]
#[derive(Clone)]
pub struct CloseUserVolumeAccumulatorEvent {
    pub user: Pubkey,
    pub timestamp: i64,
    pub total_unclaimed_tokens: u64,
    pub total_claimed_tokens: u64,
    pub current_sol_volume: u64,
    pub last_update_timestamp: i64,
}
#[event]
#[derive(Clone)]
pub struct InitUserVolumeAccumulatorEvent {
    pub payer: Pubkey,
    pub user: Pubkey,
    pub timestamp: i64,
}
#[account]
pub struct UserVolumeAccumulator {
    pub user: Pubkey,
    pub needs_claim: bool,
    pub total_unclaimed_tokens: u64,
    pub total_claimed_tokens: u64,
    pub current_sol_volume: u64,
    pub last_update_timestamp: i64,
    pub has_total_claimed_tokens: bool,
    pub cashback_earned: u64,
    pub total_cashback_claimed: u64,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct Pool {
    pub pool_bump: u8,
    pub index: u16,
    pub creator: Pubkey,
    pub base_mint: Pubkey,
    pub quote_mint: Pubkey,
    pub lp_mint: Pubkey,
    pub pool_base_token_account: Pubkey,
    pub pool_quote_token_account: Pubkey,
    pub lp_supply: u64,
    pub coin_creator: Pubkey,
    pub is_mayhem_mode: bool,
    pub is_cashback_coin: bool,
    pub virtual_quote_reserves: i128,
    pub creator_fee_bps: u64,
    pub can_edit_creator_fee: bool,
    pub is_holder_reward: bool,
    pub protocol_fees: u64,
    pub creator_fees: u64,
}

#[event]
#[derive(Clone)]
pub struct DepositEvent {
    pub timestamp: i64,
    pub lp_token_amount_out: u64,
    pub max_base_amount_in: u64,
    pub max_quote_amount_in: u64,
    pub user_base_token_reserves: u64,
    pub user_quote_token_reserves: u64,
    pub pool_base_token_reserves: u64,
    pub pool_quote_token_reserves: u64,
    pub base_amount_in: u64,
    pub quote_amount_in: u64,
    pub lp_mint_supply: u64,
    pub pool: Pubkey,
    pub user: Pubkey,
    pub user_base_token_account: Pubkey,
    pub user_quote_token_account: Pubkey,
    pub user_pool_token_account: Pubkey,
    pub quote_transfer_fee: u64,
}

#[event]
#[derive(Clone)]
pub struct WithdrawEvent {
    pub timestamp: i64,
    pub lp_token_amount_in: u64,
    pub min_base_amount_out: u64,
    pub min_quote_amount_out: u64,
    pub user_base_token_reserves: u64,
    pub user_quote_token_reserves: u64,
    pub pool_base_token_reserves: u64,
    pub pool_quote_token_reserves: u64,
    pub base_amount_out: u64,
    pub quote_amount_out: u64,
    pub lp_mint_supply: u64,
    pub pool: Pubkey,
    pub user: Pubkey,
    pub user_base_token_account: Pubkey,
    pub user_quote_token_account: Pubkey,
    pub user_pool_token_account: Pubkey,
    pub quote_transfer_fee: u64,
}

impl Owner for Pool { fn owner() -> Pubkey { crate::ID } }
impl Discriminator for Pool { const DISCRIMINATOR: &'static [u8] = &[241,154,109,4,17,177,109,188]; }
impl AccountDeserialize for Pool {
    fn try_deserialize(buf: &mut &[u8]) -> Result<Self> {
        if buf.len() < 8 || &buf[..8] != Self::DISCRIMINATOR {
            return Err(anchor_lang::solana_program::program_error::ProgramError::InvalidAccountData.into());
        }
        Self::try_deserialize_unchecked(buf)
    }
    fn try_deserialize_unchecked(buf: &mut &[u8]) -> Result<Self> {
        if buf.len() < 211 { return Err(anchor_lang::solana_program::program_error::ProgramError::InvalidAccountData.into()); }
        let n = [211,243,244,245,261,270,271,287].into_iter().filter(|n| *n <= buf.len()).last().unwrap();
        let mut padded = [0u8;287]; padded[..n].copy_from_slice(&buf[..n]);
        Self::deserialize(&mut &padded[8..]).map_err(|e| anchor_lang::solana_program::program_error::ProgramError::BorshIoError(e.to_string()).into())
    }
}
impl AccountSerialize for Pool {
    fn try_serialize<W: std::io::Write>(&self, writer: &mut W) -> Result<()> {
        writer.write_all(Self::DISCRIMINATOR)?;
        self.serialize(writer)?;
        Ok(())
    }
}
