use anchor_lang::prelude::*;
pub const PUMP_ID: Pubkey = pubkey!("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P");

/// Serialized offsets are recovered from 0x685f0 and 0x68ce0.
/// Neutral field names avoid claiming unavailable historical semantics.
#[account]
pub struct MayhemState {
    pub field_8: u64,             // 8
    pub end_timestamp: i64,        // 16: signed Clock comparison in burn
    pub mint: Pubkey,              // 24
    pub field_56: i128,            // 56: exact width; signedness not proven here
    pub field_72: i128,            // 72: exact width; signedness not proven here
    pub flag_88: bool,             // 88: decoder accepts only 0 or 1
    pub field_89: u64,             // 89
    pub status: MayhemStatus,      // 97: decoder accepts only 0, 1 or 2
    pub burned_amount: u64,        // 98
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum MayhemStatus { Variant0, Variant1, Ended }

/// A separate namespace suppresses the automatic Mayhem Owner implementation.
/// The codec at 0x6dc00 writes 82 bytes including this account discriminator.
#[account("account")]
pub struct BondingCurve {
    pub virtual_token_reserves: u64,
    pub virtual_sol_reserves: u64,
    pub real_token_reserves: u64,
    pub real_sol_reserves: u64,
    pub token_total_supply: u64,
    pub complete: bool,
    pub creator: Pubkey,
    pub is_mayhem_mode: bool,
}
impl Owner for BondingCurve { fn owner() -> Pubkey { PUMP_ID } }
