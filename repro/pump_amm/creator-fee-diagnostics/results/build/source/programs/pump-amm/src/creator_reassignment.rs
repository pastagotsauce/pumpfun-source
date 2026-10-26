use crate::*;
use anchor_lang::Discriminator;
use anchor_spl::metadata::MetadataAccount;
pub const FEES_PROGRAM: Pubkey = anchor_lang::solana_program::pubkey!("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ");
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]pub enum ConfigStatus{Paused,Active}
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]pub struct Shareholder{pub address:Pubkey,pub share_bps:u16}
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]pub struct SharingConfig{pub bump:u8,pub version:u8,pub status:ConfigStatus,pub mint:Pubkey,pub admin:Pubkey,pub admin_revoked:bool,pub shareholders:Vec<Shareholder>}
impl Owner for SharingConfig{fn owner()->Pubkey{FEES_PROGRAM}}
impl Discriminator for SharingConfig{const DISCRIMINATOR:&'static[u8]=&[216,74,9,0,56,140,93,75];}
impl AccountSerialize for SharingConfig{}
impl AccountDeserialize for SharingConfig{
 fn try_deserialize(buf:&mut &[u8])->Result<Self>{if buf.len()<8{return Err(error!(anchor_lang::error::ErrorCode::AccountDiscriminatorNotFound));}if &buf[..8]!=Self::DISCRIMINATOR{return Err(error!(anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch));}Self::try_deserialize_unchecked(buf)}
 fn try_deserialize_unchecked(buf:&mut &[u8])->Result<Self>{Self::deserialize(&mut &buf[8..]).map_err(|_|error!(anchor_lang::error::ErrorCode::AccountDidNotDeserialize))}
}
#[derive(AnchorSerialize,AnchorDeserialize,Clone)]pub struct BondingCurve{pub virtual_token_reserves:u64,pub virtual_sol_reserves:u64,pub real_token_reserves:u64,pub real_sol_reserves:u64,pub token_total_supply:u64,pub complete:bool,pub creator:Pubkey,pub is_mayhem_mode:bool,pub is_cashback_coin:bool}
impl Owner for BondingCurve{fn owner()->Pubkey{trade::PUMP}}
impl Discriminator for BondingCurve{const DISCRIMINATOR:&'static[u8]=&[23,183,248,55,96,216,172,96];}
impl AccountSerialize for BondingCurve{}
impl AccountDeserialize for BondingCurve{
 fn try_deserialize(buf:&mut &[u8])->Result<Self>{if buf.len()<8{return Err(error!(anchor_lang::error::ErrorCode::AccountDiscriminatorNotFound));}if &buf[..8]!=Self::DISCRIMINATOR{return Err(error!(anchor_lang::error::ErrorCode::AccountDiscriminatorMismatch));}Self::try_deserialize_unchecked(buf)}
 fn try_deserialize_unchecked(buf:&mut &[u8])->Result<Self>{Self::deserialize(&mut &buf[8..]).map_err(|_|error!(anchor_lang::error::ErrorCode::AccountDidNotDeserialize))}
}
#[event_cpi]
#[derive(Accounts)]
pub struct MigratePoolCoinCreator<'info>{
 #[account(mut,seeds=[b"pool",pool.index.to_le_bytes().as_ref(),pool.creator.as_ref(),pool.base_mint.as_ref(),pool.quote_mint.as_ref()],bump)]pub pool:Box<Account<'info,Pool>>,
 #[account(seeds=[b"sharing-config",pool.base_mint.as_ref()],bump,seeds::program=FEES_PROGRAM,constraint=sharing_config.mint==pool.base_mint @ PumpAmmError::InvalidSharingConfigBaseMint,constraint=sharing_config.admin==pool.coin_creator @ PumpAmmError::InvalidSharingConfigCoinCreator)]pub sharing_config:Box<Account<'info,SharingConfig>>,
}
pub fn migrate(ctx:Context<MigratePoolCoinCreator>)->Result<()>{
 let pool=&mut ctx.accounts.pool;
 require!(!pool.is_holder_reward,PumpAmmError::HolderRewardCreatorImmutable);
 require!(pool.creator_fees==0,PumpAmmError::CreatorFeesNotSwept);
 let old_coin_creator=pool.coin_creator;pool.coin_creator=ctx.accounts.sharing_config.key();
 let event=MigratePoolCoinCreatorEvent{timestamp:Clock::get()?.unix_timestamp,base_mint:pool.base_mint,pool:pool.key(),sharing_config:ctx.accounts.sharing_config.key(),old_coin_creator,new_coin_creator:pool.coin_creator};emit!(event.clone());emit_cpi!(event);Ok(())
}
#[event_cpi]
#[derive(Accounts)]
pub struct SetCoinCreator<'info>{
 #[account(mut)]pub pool:Box<Account<'info,Pool>>,
 #[account(seeds=[b"metadata",anchor_spl::metadata::ID.as_ref(),pool.base_mint.as_ref()],bump,seeds::program=anchor_spl::metadata::ID)]pub metadata:Box<Account<'info,MetadataAccount>>,
 #[account(seeds=[b"bonding-curve",pool.base_mint.as_ref()],bump,seeds::program=trade::PUMP)]pub bonding_curve:Box<Account<'info,BondingCurve>>,
}
pub fn set(ctx:Context<SetCoinCreator>)->Result<()>{
 let pool=&mut ctx.accounts.pool;
 let authority=Pubkey::find_program_address(&[b"pool-authority",pool.base_mint.as_ref()],&trade::PUMP).0;
 require_keys_eq!(pool.creator,authority,PumpAmmError::OnlyCanonicalPumpPoolsCanHaveCoinCreator);
 if pool.coin_creator!=Pubkey::default(){msg!("Pool has coin_creator already set");return Ok(())}
 if let Some(creators)=&ctx.accounts.metadata.creators{
  pool.coin_creator=creators[0].address;
  let event=SetMetaplexCoinCreatorEvent{timestamp:Clock::get()?.unix_timestamp,base_mint:pool.base_mint,pool:pool.key(),metadata:ctx.accounts.metadata.key(),coin_creator:pool.coin_creator};emit!(event.clone());emit_cpi!(event);
 }else{
  pool.coin_creator=ctx.accounts.bonding_curve.creator;
  let event=SetBondingCurveCoinCreatorEvent{timestamp:Clock::get()?.unix_timestamp,base_mint:pool.base_mint,pool:pool.key(),bonding_curve:ctx.accounts.bonding_curve.key(),coin_creator:pool.coin_creator};emit!(event.clone());emit_cpi!(event);
 }Ok(())
}
#[event]#[derive(Clone)]pub struct MigratePoolCoinCreatorEvent{pub timestamp:i64,pub base_mint:Pubkey,pub pool:Pubkey,pub sharing_config:Pubkey,pub old_coin_creator:Pubkey,pub new_coin_creator:Pubkey}
#[event]#[derive(Clone)]pub struct SetMetaplexCoinCreatorEvent{pub timestamp:i64,pub base_mint:Pubkey,pub pool:Pubkey,pub metadata:Pubkey,pub coin_creator:Pubkey}
#[event]#[derive(Clone)]pub struct SetBondingCurveCoinCreatorEvent{pub timestamp:i64,pub base_mint:Pubkey,pub pool:Pubkey,pub bonding_curve:Pubkey,pub coin_creator:Pubkey}

#[event_cpi]
#[derive(Accounts)]
pub struct AdminCtoPool<'info>{
 #[account(mut)]pub payer:Signer<'info>,
 pub global_config:Box<Account<'info,GlobalConfig>>,
 #[account(mut)]pub pool:Box<Account<'info,Pool>>,
 #[account(seeds=[b"pool-authority",pool.base_mint.as_ref()],bump,seeds::program=trade::PUMP)]pub pool_authority:Signer<'info>,
 pub system_program:Program<'info,System>,
}
pub fn admin_cto(ctx:Context<AdminCtoPool>,coin_creator:Pubkey,is_holder_reward:bool,creator_fee_bps:Option<u64>)->Result<()>{
 let info=ctx.accounts.pool.to_account_info();
 if info.data_len()<287{
  let needed=Rent::get()?.minimum_balance(287).saturating_sub(info.lamports());
  if needed>0{anchor_lang::system_program::transfer(CpiContext::new(ctx.accounts.system_program.to_account_info(),anchor_lang::system_program::Transfer{from:ctx.accounts.payer.to_account_info(),to:info.clone()}),needed)?;}
  info.realloc(287,false)?;
 }
 let pool=&mut ctx.accounts.pool;
 require_keys_eq!(pool.creator,ctx.accounts.pool_authority.key(),PumpAmmError::OnlyCanonicalPumpPoolsCanHaveCoinCreator);
 require!(!pool.is_mayhem_mode,PumpAmmError::CtoNotAllowedForMayhemPool);
 require!(!pool.is_holder_reward || is_holder_reward,PumpAmmError::HolderRewardCreatorImmutable);
 if is_holder_reward{
  require_keys_eq!(coin_creator,Pubkey::find_program_address(&[b"holder-rewards",pool.base_mint.as_ref()],&trade::PUMP).0,PumpAmmError::InvalidHolderRewardCoinCreator);
 }
 if is_holder_reward{pool.is_cashback_coin=false;}
 if let Some(fee)=creator_fee_bps{
  require!(pool.quote_mint!=anchor_spl::token::spl_token::native_mint::ID && pool.quote_mint!=anchor_lang::solana_program::pubkey!("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),PumpAmmError::CreatorFeeNotConfigurableForQuote);
  require!(!pool.is_cashback_coin,PumpAmmError::CreatorFeeNotAllowedForCashbackCoin);
  require!(ctx.accounts.global_config.creator_fee_configurable,PumpAmmError::CreatorFeeNotConfigurable);
  require!(fee>0 && fee<=ctx.accounts.global_config.max_configurable_creator_fee_bps,PumpAmmError::CreatorFeeBpsOutOfRange);
 }
 require_eq!(pool.creator_fees,0,PumpAmmError::CreatorFeesNotSwept);
 let old_coin_creator=pool.coin_creator;let old_creator_fee_bps=pool.creator_fee_bps;
 pool.coin_creator=coin_creator;pool.is_holder_reward=is_holder_reward;pool.can_edit_creator_fee=false;
 if let Some(fee)=creator_fee_bps{pool.creator_fee_bps=fee;}
 let event=AdminCtoPoolEvent{timestamp:Clock::get()?.unix_timestamp,base_mint:pool.base_mint,pool:pool.key(),old_coin_creator,new_coin_creator:coin_creator,is_holder_reward,is_cashback_coin:pool.is_cashback_coin,old_creator_fee_bps,new_creator_fee_bps:pool.creator_fee_bps};emit!(event.clone());emit_cpi!(event);Ok(())
}
#[event]#[derive(Clone)]pub struct AdminCtoPoolEvent{pub timestamp:i64,pub base_mint:Pubkey,pub pool:Pubkey,pub old_coin_creator:Pubkey,pub new_coin_creator:Pubkey,pub is_holder_reward:bool,pub is_cashback_coin:bool,pub old_creator_fee_bps:u64,pub new_creator_fee_bps:u64}
