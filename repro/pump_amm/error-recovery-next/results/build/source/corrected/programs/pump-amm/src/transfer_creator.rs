use crate::*;
use anchor_spl::{associated_token::{self,AssociatedToken},token_interface::TokenInterface};
#[event_cpi]
#[derive(Accounts)]
pub struct TransferCreatorFeesToPump<'info> {
 #[account(address=anchor_spl::token::spl_token::native_mint::ID @ PumpAmmError::UnsupportedQuoteMint)]
 pub wsol_mint: Box<InterfaceAccount<'info,Mint>>,
 pub token_program: Interface<'info,TokenInterface>,
 pub system_program: Program<'info,System>,
 pub associated_token_program: Program<'info,AssociatedToken>,
 /// CHECK: only its key derives the receiving vault.
 pub coin_creator: UncheckedAccount<'info>,
 /// CHECK: PDA signer constrained by seeds.
 #[account(mut,seeds=[b"creator_vault",coin_creator.key().as_ref()],bump)]
 pub coin_creator_vault_authority: UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=wsol_mint,associated_token::authority=coin_creator_vault_authority,associated_token::token_program=token_program)]
 pub coin_creator_vault_ata: Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: destination is the canonical Pump creator vault PDA.
 #[account(mut,seeds=[b"creator-vault",coin_creator.key().as_ref()],bump,seeds::program=crate::trade::PUMP)]
 pub pump_creator_vault: UncheckedAccount<'info>,
}
#[event_cpi]
#[derive(Accounts)]
pub struct TransferCreatorFeesToPumpV2<'info> {
 #[account(mut)] pub payer: Signer<'info>,
 pub quote_mint: Box<InterfaceAccount<'info,Mint>>,
 pub token_program: Interface<'info,TokenInterface>,
 pub system_program: Program<'info,System>,
 pub associated_token_program: Program<'info,AssociatedToken>,
 /// CHECK: only its key derives the receiving vault.
 pub coin_creator: UncheckedAccount<'info>,
 /// CHECK: PDA signer constrained by seeds.
 #[account(mut,seeds=[b"creator_vault",coin_creator.key().as_ref()],bump)]
 pub coin_creator_vault_authority: UncheckedAccount<'info>,
 #[account(mut,associated_token::mint=quote_mint,associated_token::authority=coin_creator_vault_authority,associated_token::token_program=token_program)]
 pub coin_creator_vault_ata: Box<InterfaceAccount<'info,TokenAccount>>,
 /// CHECK: destination is the canonical Pump creator vault PDA.
 #[account(mut,seeds=[b"creator-vault",coin_creator.key().as_ref()],bump,seeds::program=crate::trade::PUMP)]
 pub pump_creator_vault: UncheckedAccount<'info>,
 /// CHECK: address constrained; handler creates it for non-native quotes.
 #[account(mut,seeds=[pump_creator_vault.key().as_ref(),token_program.key().as_ref(),quote_mint.key().as_ref()],bump,seeds::program=associated_token_program.key())]
 pub pump_creator_vault_ata: UncheckedAccount<'info>,
}
pub fn legacy(ctx:Context<TransferCreatorFeesToPump>)->Result<()> {
 let a=&ctx.accounts;let creator=a.coin_creator.key();let bump=[ctx.bumps.coin_creator_vault_authority];let seeds:&[&[u8]]=&[b"creator_vault",creator.as_ref(),&bump];
 unwrap_and_move(a.wsol_mint.to_account_info(),a.token_program.to_account_info(),a.system_program.to_account_info(),a.associated_token_program.to_account_info(),a.coin_creator_vault_authority.to_account_info(),a.coin_creator_vault_ata.to_account_info(),a.pump_creator_vault.to_account_info(),seeds)
}
pub fn v2(ctx:Context<TransferCreatorFeesToPumpV2>)->Result<()> {
 let a=&ctx.accounts;let creator=a.coin_creator.key();let bump=[ctx.bumps.coin_creator_vault_authority];let seeds:&[&[u8]]=&[b"creator_vault",creator.as_ref(),&bump];
 if a.quote_mint.key()==anchor_spl::token::spl_token::native_mint::ID {return unwrap_and_move(a.quote_mint.to_account_info(),a.token_program.to_account_info(),a.system_program.to_account_info(),a.associated_token_program.to_account_info(),a.coin_creator_vault_authority.to_account_info(),a.coin_creator_vault_ata.to_account_info(),a.pump_creator_vault.to_account_info(),seeds)}
 if a.pump_creator_vault_ata.data_is_empty(){associated_token::create(CpiContext::new(a.associated_token_program.to_account_info(),associated_token::Create{payer:a.payer.to_account_info(),associated_token:a.pump_creator_vault_ata.to_account_info(),authority:a.pump_creator_vault.to_account_info(),mint:a.quote_mint.to_account_info(),system_program:a.system_program.to_account_info(),token_program:a.token_program.to_account_info()}))?;}
 token_interface::transfer_checked(CpiContext::new_with_signer(a.token_program.to_account_info(),token_interface::TransferChecked{from:a.coin_creator_vault_ata.to_account_info(),mint:a.quote_mint.to_account_info(),to:a.pump_creator_vault_ata.to_account_info(),authority:a.coin_creator_vault_authority.to_account_info()},&[seeds]),a.coin_creator_vault_ata.amount,a.quote_mint.decimals)
}
#[inline(never)]
fn unwrap_and_move<'info>(mint:AccountInfo<'info>,token_program:AccountInfo<'info>,system_program:AccountInfo<'info>,associated_program:AccountInfo<'info>,authority:AccountInfo<'info>,vault:AccountInfo<'info>,destination:AccountInfo<'info>,seeds:&[&[u8]])->Result<()> {
 let rent=Rent::get()?;let minimum=rent.minimum_balance(165).checked_add(rent.minimum_balance(destination.data_len()).saturating_sub(destination.lamports())).ok_or(PumpAmmError::Overflow)?;
 if vault.lamports()<minimum {msg!("Available fees ({}) below minimum transfer amount ({}):",vault.lamports(),minimum);return Ok(())}
 token_interface::close_account(CpiContext::new_with_signer(token_program.clone(),token_interface::CloseAccount{account:vault.clone(),destination:authority.clone(),authority:authority.clone()},&[seeds]))?;
 associated_token::create(CpiContext::new_with_signer(associated_program,associated_token::Create{payer:authority.clone(),associated_token:vault,authority:authority.clone(),mint,system_program:system_program.clone(),token_program},&[seeds]))?;
 let amount=authority.lamports();anchor_lang::system_program::transfer(CpiContext::new_with_signer(system_program,anchor_lang::system_program::Transfer{from:authority,to:destination},&[seeds]),amount)
}
