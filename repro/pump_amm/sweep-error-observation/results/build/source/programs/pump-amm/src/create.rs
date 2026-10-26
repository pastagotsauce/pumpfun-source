use crate::*;
use anchor_spl::associated_token::AssociatedToken;
use anchor_spl::token_interface::TokenInterface;
use std::io::{Read, Write};
#[derive(Clone)]
pub struct OptionBool(pub bool);
impl AnchorSerialize for OptionBool {
    fn serialize<W: Write>(&self, w: &mut W) -> std::io::Result<()> {
        self.0.serialize(w)
    }
}
impl AnchorDeserialize for OptionBool {
    fn deserialize_reader<R: Read>(r: &mut R) -> std::io::Result<Self> {
        let mut a = [0];
        match r.read_exact(&mut a) {
            Ok(()) => match a[0] {
                0 => Ok(Self(false)),
                1 => Ok(Self(true)),
                _ => Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "Invalid bool representation",
                )),
            },
            Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => Ok(Self(false)),
            Err(e) => Err(e),
        }
    }
}
#[derive(Clone)]
pub struct OptionU64(pub u64);
impl AnchorSerialize for OptionU64 {
    fn serialize<W: Write>(&self, w: &mut W) -> std::io::Result<()> {
        self.0.serialize(w)
    }
}
impl AnchorDeserialize for OptionU64 {
    fn deserialize_reader<R: Read>(r: &mut R) -> std::io::Result<Self> {
        let mut a = [0; 8];
        let mut n = 0;
        while n < 8 {
            let count = r.read(&mut a[n..])?;
            if count == 0 {
                break;
            }
            n += count;
        }
        Ok(Self(u64::from_le_bytes(a)))
    }
}
#[event_cpi]
#[derive(Accounts)]
#[instruction(index:u16)]
pub struct CreatePool<'info> {
    #[account(init,payer=creator,space=287,seeds=[b"pool",index.to_le_bytes().as_ref(),creator.key().as_ref(),base_mint.key().as_ref(),quote_mint.key().as_ref()],bump)]
    pub pool: Box<Account<'info, Pool>>,
    pub global_config: Box<Account<'info, GlobalConfig>>,
    #[account(mut)]
    pub creator: Signer<'info>,
    pub base_mint: Box<InterfaceAccount<'info, Mint>>,
    pub quote_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(init,payer=creator,seeds=[b"pool_lp_mint",pool.key().as_ref()],bump,mint::decimals=9,mint::authority=pool,mint::token_program=token_2022_program)]
    pub lp_mint: Box<InterfaceAccount<'info, Mint>>,
    #[account(mut)]
    pub user_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(mut)]
    pub user_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(init,payer=creator,associated_token::mint=lp_mint,associated_token::authority=creator,associated_token::token_program=token_2022_program)]
    pub user_pool_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(init_if_needed,payer=creator,associated_token::mint=base_mint,associated_token::authority=pool,associated_token::token_program=base_token_program)]
    pub pool_base_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    #[account(init_if_needed,payer=creator,associated_token::mint=quote_mint,associated_token::authority=pool,associated_token::token_program=quote_token_program)]
    pub pool_quote_token_account: Box<InterfaceAccount<'info, TokenAccount>>,
    pub system_program: Program<'info, System>,
    pub token_2022_program: Program<'info, Token2022>,
    pub base_token_program: Interface<'info, TokenInterface>,
    pub quote_token_program: Interface<'info, TokenInterface>,
    pub associated_token_program: Program<'info, AssociatedToken>,
}
#[inline(never)]
pub fn execute(
    ctx: Context<CreatePool>,
    index: u16,
    base_in: u64,
    quote_in: u64,
    coin_creator: Pubkey,
    mayhem: bool,
    cashback: bool,
    creator_fee: u64,
    can_edit: bool,
    holder: bool,
) -> Result<()> {
    let a = &mut *ctx.accounts;
    require!(
        a.global_config.disable_flags & 1 == 0,
        PumpAmmError::DisabledCreatePool
    );
    require!(base_in > 0, PumpAmmError::ZeroBaseAmount);
    require!(quote_in > 0, PumpAmmError::ZeroQuoteAmount);
    require!(
        supported_mint(&a.base_mint.to_account_info())?,
        PumpAmmError::UnsupportedBaseMint
    );
    require!(
        supported_mint(&a.quote_mint.to_account_info())?,
        PumpAmmError::UnsupportedQuoteMint
    );
    require_keys_neq!(
        a.base_mint.key(),
        a.quote_mint.key(),
        PumpAmmError::SameMint
    );
    let pump = Pubkey::new_from_array([
        1, 86, 224, 246, 147, 102, 90, 207, 68, 219, 21, 104, 191, 23, 91, 170, 81, 137, 203, 151,
        245, 210, 255, 59, 101, 93, 43, 182, 253, 109, 24, 176,
    ]);
    let canonical =
        Pubkey::find_program_address(&[b"pool-authority", a.base_mint.key().as_ref()], &pump).0
            == a.creator.key();
    require!(
        !mayhem || a.global_config.mayhem_mode_enabled,
        PumpAmmError::MayhemModeDisabled
    );
    require!(!mayhem || canonical, PumpAmmError::OnlyPumpPoolsMayhemMode);
    require!(
        !cashback || a.global_config.is_cashback_enabled,
        PumpAmmError::CashbackNotEnabled
    );
    require!(!cashback || canonical, PumpAmmError::OnlyPumpPoolsCashback);

    for (src, mint, dst, program, amount) in [
        (
            a.user_base_token_account.to_account_info(),
            a.base_mint.to_account_info(),
            a.pool_base_token_account.to_account_info(),
            a.base_token_program.to_account_info(),
            base_in,
        ),
        (
            a.user_quote_token_account.to_account_info(),
            a.quote_mint.to_account_info(),
            a.pool_quote_token_account.to_account_info(),
            a.quote_token_program.to_account_info(),
            quote_in,
        ),
    ] {
        let decimals = if mint.key() == a.base_mint.key() {
            a.base_mint.decimals
        } else {
            a.quote_mint.decimals
        };
        token_interface::transfer_checked(
            CpiContext::new(
                program,
                token_interface::TransferChecked {
                    from: src,
                    mint,
                    to: dst,
                    authority: a.creator.to_account_info(),
                },
            ),
            amount,
            decimals,
        )?;
    }
    a.pool_base_token_account.reload()?;
    a.pool_quote_token_account.reload()?;
    let pb = a.pool_base_token_account.amount;
    let pq = a.pool_quote_token_account.amount;
    let product = (pb as u128) * (pq as u128);
    let mut low = 0u128;
    let mut high = 1u128 << 64;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if mid * mid <= product {
            low = mid
        } else {
            high = mid
        }
    }
    require!(
        (creator_fee == 0 && !can_edit) || canonical,
        PumpAmmError::OnlyCanonicalPumpPoolsCanHaveCoinCreator
    );
    let liquidity = low as u64;
    require!(liquidity >= 100, PumpAmmError::TooLittlePoolTokenLiquidity);
    let output = liquidity - 100;
    let creator = a.creator.key();
    let base = a.base_mint.key();
    let quote = a.quote_mint.key();
    let idx = index.to_le_bytes();
    let bump = [ctx.bumps.pool];
    let seeds: &[&[u8]] = &[
        b"pool",
        &idx,
        creator.as_ref(),
        base.as_ref(),
        quote.as_ref(),
        &bump,
    ];
    anchor_spl::token_2022::mint_to(
        CpiContext::new_with_signer(
            a.token_2022_program.to_account_info(),
            anchor_spl::token_2022::MintTo {
                mint: a.lp_mint.to_account_info(),
                to: a.user_pool_token_account.to_account_info(),
                authority: a.pool.to_account_info(),
            },
            &[seeds],
        ),
        output,
    )?;
    a.pool.set_inner(Pool {
        pool_bump: bump[0],
        index,
        creator,
        base_mint: base,
        quote_mint: quote,
        lp_mint: a.lp_mint.key(),
        pool_base_token_account: a.pool_base_token_account.key(),
        pool_quote_token_account: a.pool_quote_token_account.key(),
        lp_supply: liquidity,
        coin_creator: if canonical {
            coin_creator
        } else {
            Pubkey::default()
        },
        is_mayhem_mode: mayhem,
        is_cashback_coin: cashback,
        virtual_quote_reserves: 0,
        creator_fee_bps: creator_fee,
        can_edit_creator_fee: can_edit,
        is_holder_reward: canonical && holder,
        protocol_fees: 0,
        creator_fees: 0,
    });
    let event = CreatePoolEvent {
        timestamp: Clock::get()?.unix_timestamp,
        index,
        creator,
        base_mint: base,
        quote_mint: quote,
        base_mint_decimals: a.base_mint.decimals,
        quote_mint_decimals: a.quote_mint.decimals,
        base_amount_in: base_in,
        quote_amount_in: quote_in,
        pool_base_amount: pb,
        pool_quote_amount: pq,
        minimum_liquidity: 100,
        initial_liquidity: liquidity,
        lp_token_amount_out: output,
        pool_bump: bump[0],
        pool: a.pool.key(),
        lp_mint: a.lp_mint.key(),
        user_base_token_account: a.user_base_token_account.key(),
        user_quote_token_account: a.user_quote_token_account.key(),
        coin_creator,
        is_mayhem_mode: mayhem,
        creator_fee_bps: creator_fee,
        can_edit_creator_fee: can_edit,
        is_holder_reward: a.pool.is_holder_reward,
    };
    emit!(event.clone());
    emit_cpi!(event);
    Ok(())
}

#[event]
#[derive(Clone)]
pub struct CreatePoolEvent {
    pub timestamp: i64,
    pub index: u16,
    pub creator: Pubkey,
    pub base_mint: Pubkey,
    pub quote_mint: Pubkey,
    pub base_mint_decimals: u8,
    pub quote_mint_decimals: u8,
    pub base_amount_in: u64,
    pub quote_amount_in: u64,
    pub pool_base_amount: u64,
    pub pool_quote_amount: u64,
    pub minimum_liquidity: u64,
    pub initial_liquidity: u64,
    pub lp_token_amount_out: u64,
    pub pool_bump: u8,
    pub pool: Pubkey,
    pub lp_mint: Pubkey,
    pub user_base_token_account: Pubkey,
    pub user_quote_token_account: Pubkey,
    pub coin_creator: Pubkey,
    pub is_mayhem_mode: bool,
    pub creator_fee_bps: u64,
    pub can_edit_creator_fee: bool,
    pub is_holder_reward: bool,
}

fn supported_mint(info: &AccountInfo) -> Result<bool> {
    use anchor_spl::token_2022::spl_token_2022::{
        extension::{BaseStateWithExtensions, ExtensionType, StateWithExtensions},
        state::Mint as SplMint,
    };
    if *info.owner == anchor_spl::token::ID {
        return Ok(true);
    }
    let data = info.try_borrow_data()?;
    let mint = StateWithExtensions::<SplMint>::unpack(&data)?;
    Ok(mint.get_extension_types()?.iter().all(|e| {
        matches!(
            e,
            ExtensionType::MetadataPointer | ExtensionType::TokenMetadata
        )
    }))
}
