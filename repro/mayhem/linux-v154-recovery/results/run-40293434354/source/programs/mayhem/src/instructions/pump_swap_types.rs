//! External AMM codecs recovered from original Mayhem decoding routines.
use anchor_lang::prelude::*;
use anchor_lang::Discriminator;
pub const AMM_ID:Pubkey=pubkey!("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA");
// 0x17d8 computes current serialized size 287 from the default struct, allocates a
// ZERO-filled 287-byte buffer for every shorter input, copies ALL available input
// bytes, then calls 0x8eb78. No version-boundary truncation is used in Mayhem.
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]
pub struct SwapPool {
 pub pool_bump:u8,                  // 8
 pub index:u16,                     // 9
 pub creator:Pubkey,                // 11
 pub base_mint:Pubkey,              // 43
 pub quote_mint:Pubkey,             // 75
 pub lp_mint:Pubkey,                // 107
 pub pool_base_token_account:Pubkey,// 139
 pub pool_quote_token_account:Pubkey,//171
 pub lp_supply:u64,                 // 203
 pub coin_creator:Pubkey,           // 211
 pub is_mayhem_mode:bool,           // 243
 pub is_cashback_coin:bool,         // 244
 pub virtual_quote_reserves:i128,   // 245
 pub creator_fee_bps:u64,           // 261
 pub can_edit_creator_fee:bool,     // 269
 pub is_holder_reward:bool,         // 270
 pub protocol_fees:u64,             // 271
 pub creator_fees:u64,              // 279, end287
}
impl Owner for SwapPool {fn owner()->Pubkey{AMM_ID}}
impl Discriminator for SwapPool {const DISCRIMINATOR:&'static[u8]=&[241,154,109,4,17,177,109,188];}
impl AccountDeserialize for SwapPool {
 fn try_deserialize(buf:&mut &[u8])->Result<Self>{
  let mut padded=[0u8;287];let data=if buf.len()<287{padded[..buf.len()].copy_from_slice(buf);&padded[..]}else{*buf};
  // Padding precedes discriminator validation: inputs shorter than8 reject as
  // AccountDiscriminatorMismatch (unless all8 discriminator bytes are present).
  if &data[..8]!=Self::DISCRIMINATOR{return Err(anchor_lang::error::Error::from(anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch).with_account_name("Pool"));}
  Self::deserialize(&mut &data[8..]).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotDeserialize.into())
 }
 fn try_deserialize_unchecked(buf:&mut &[u8])->Result<Self>{
  let mut padded=[0u8;287];let data=if buf.len()<287{padded[..buf.len()].copy_from_slice(buf);&padded[..]}else{*buf};
  Self::deserialize(&mut &data[8..]).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotDeserialize.into())
 }
}
impl AccountSerialize for SwapPool {
 fn try_serialize<W:std::io::Write>(&self,w:&mut W)->Result<()>{w.write_all(Self::DISCRIMINATOR).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotSerialize)?;self.serialize(w).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotSerialize.into())}
}
// 0x744a8 checks discriminator; 0x74890 consumes exactly the old418-byte prefix.
// Unlike Pool this has no padding and no optional historical layout selector.
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]
pub struct SwapGlobalConfig {
 pub admin:Pubkey,                         // 8
 pub lp_fee_basis_points:u64,              // 40
 pub protocol_fee_basis_points:u64,        // 48
 pub disable_flags:u8,                    // 56
 pub protocol_fee_recipients:[Pubkey;8],   // 57
 pub coin_creator_fee_basis_points:u64,    // 313
 pub admin_set_coin_creator_authority:Pubkey,//321
 pub whitelist_pda:Pubkey,                // 353
 pub reserved_fee_recipient:Pubkey,        // 385
 pub mayhem_mode_enabled:bool,            // 417, end418
}
impl Owner for SwapGlobalConfig {fn owner()->Pubkey{AMM_ID}}
impl Discriminator for SwapGlobalConfig {const DISCRIMINATOR:&'static[u8]=&[149,8,156,202,160,252,176,217];}
impl AccountDeserialize for SwapGlobalConfig {
 fn try_deserialize(buf:&mut &[u8])->Result<Self>{
  if buf.len()<8{return Err(anchor_lang::error::ErrorCode::AccountDiscriminatorNotFound.into());}
  if &buf[..8]!=Self::DISCRIMINATOR{return Err(anchor_lang::error::Error::from(anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch).with_account_name("GlobalConfig"));}
  Self::try_deserialize_unchecked(buf)
 }
 fn try_deserialize_unchecked(buf:&mut &[u8])->Result<Self>{
  if buf.len()<8{return Err(anchor_lang::error::ErrorCode::AccountDidNotDeserialize.into());}
  Self::deserialize(&mut &buf[8..]).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotDeserialize.into())
 }
}
impl AccountSerialize for SwapGlobalConfig {
 fn try_serialize<W:std::io::Write>(&self,w:&mut W)->Result<()>{w.write_all(Self::DISCRIMINATOR).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotSerialize)?;self.serialize(w).map_err(|_|anchor_lang::error::ErrorCode::AccountDidNotSerialize.into())}
}

#[error_code]
pub enum PumpSwapError {
 #[msg("Pump Swap CPI call failed")]PumpSwapCpiFailed=10,
 #[msg("Math Overflow in Pump Swap CPI call")]PumpSwapCpiMathOverflow=11,
}
