use crate::*;
use anchor_spl::{associated_token::AssociatedToken, token_interface::{TokenInterface, TransferChecked}};

#[account]
#[derive(Debug)]
pub struct GlobalVolumeAccumulator {
    pub start_time:i64,
    pub end_time:i64,
    pub seconds_in_a_day:i64,
    pub mint:Pubkey,
    pub total_token_supply:[u64;30],
    pub sol_volumes:[u64;30],
}
#[event_cpi]
#[derive(Accounts)]
pub struct SyncUserVolumeAccumulator<'info>{
    /// CHECK: PDA seed only, no signature required.
    pub user:AccountInfo<'info>,
    #[account(seeds=[b"global_volume_accumulator"],bump)]
    pub global_volume_accumulator:Account<'info,GlobalVolumeAccumulator>,
    #[account(mut,seeds=[b"user_volume_accumulator",user.key().as_ref()],bump)]
    pub user_volume_accumulator:Account<'info,UserVolumeAccumulator>,
}
fn reset(g:&GlobalVolumeAccumulator,u:&mut UserVolumeAccumulator,now:i64){
    if now<g.start_time && u.last_update_timestamp<g.start_time {
        u.total_claimed_tokens=0;
        u.has_total_claimed_tokens=false;
    }
}
pub fn sync(ctx:Context<SyncUserVolumeAccumulator>)->Result<()> {
    let timestamp=Clock::get()?.unix_timestamp;
    let before=ctx.accounts.user_volume_accumulator.total_claimed_tokens;
    reset(&ctx.accounts.global_volume_accumulator,&mut ctx.accounts.user_volume_accumulator,timestamp);
    let after=ctx.accounts.user_volume_accumulator.total_claimed_tokens;
    if before!=after {
        let event=SyncUserVolumeAccumulatorEvent{user:ctx.accounts.user.key(),total_claimed_tokens_before:before,total_claimed_tokens_after:after,timestamp};
        emit!(event.clone());emit_cpi!(event);
    }else{
        msg!("No changes in accumulator for user={}",ctx.accounts.user.key());
    }
    Ok(())
}
#[event_cpi]
#[derive(Accounts)]
pub struct AdminUpdateTokenIncentives<'info>{
    #[account(mut)] pub admin:Signer<'info>,
    #[account(seeds=[b"global_config"],bump,has_one=admin @ PumpAmmError::InvalidAdmin)]
    pub global_config:Box<Account<'info,GlobalConfig>>,
    #[account(mut,seeds=[b"global_volume_accumulator"],bump)]
    pub global_volume_accumulator:Box<Account<'info,GlobalVolumeAccumulator>>,
    pub mint:InterfaceAccount<'info,Mint>,
    #[account(init_if_needed,payer=admin,associated_token::mint=mint,associated_token::authority=global_volume_accumulator,associated_token::token_program=token_program)]
    pub global_incentive_token_account:InterfaceAccount<'info,TokenAccount>,
    pub associated_token_program:Program<'info,AssociatedToken>,
    pub system_program:Program<'info,System>,
    pub token_program:Interface<'info,TokenInterface>,
}
pub fn admin(ctx:Context<AdminUpdateTokenIncentives>,start_time:i64,end_time:i64,seconds_in_a_day:i64,day_number:u64,token_supply_per_day:u64)->Result<()> {
    let timestamp=Clock::get()?.unix_timestamp;
    let g=&mut ctx.accounts.global_volume_accumulator;
    g.mint=ctx.accounts.mint.key();g.seconds_in_a_day=seconds_in_a_day;
    if start_time!=0 && end_time!=0 {
        if start_time!=g.start_time {
            require!(start_time>timestamp,PumpAmmError::StartTimeInThePast);
            g.start_time=start_time;g.total_token_supply=[0;30];g.sol_volumes=[0;30];
        }
        require!(end_time>timestamp,PumpAmmError::EndTimeInThePast);
        require!(end_time>start_time,PumpAmmError::EndTimeBeforeStartTime);
        require!(end_time-start_time<seconds_in_a_day*30,PumpAmmError::TimeRangeTooLarge);
        g.end_time=end_time;
        if timestamp>g.start_time {
            let current=usize::try_from((timestamp-g.start_time)/seconds_in_a_day).unwrap();
            let end=usize::try_from((g.end_time-g.start_time)/seconds_in_a_day).unwrap();
            require!(end>current,PumpAmmError::EndTimeBeforeCurrentDay);
            for i in current+1..=end {g.sol_volumes[i]=0;}
        }
    }
    if token_supply_per_day>0 {
        require!(timestamp<=g.end_time,PumpAmmError::SupplyUpdateForFinishedRange);
        let current=if timestamp<g.start_time {0}else{usize::try_from((timestamp-g.start_time)/seconds_in_a_day).unwrap()};
        let end=usize::try_from((g.end_time-g.start_time)/seconds_in_a_day).unwrap();
        if day_number<30 {
            require!(day_number as usize<=end,PumpAmmError::DayIndexAfterEndIndex);
            require!(day_number as usize>=current,PumpAmmError::DayInActiveRange);
            g.total_token_supply[day_number as usize]=token_supply_per_day;
        }else{for i in current..=end {g.total_token_supply[i]=token_supply_per_day;}}
    }
    let event=AdminUpdateTokenIncentivesEvent{start_time,end_time,day_number,token_supply_per_day,mint:ctx.accounts.mint.key(),seconds_in_a_day,timestamp};
    emit!(event.clone());emit_cpi!(event);
    Ok(())
}
#[derive(Accounts)]
pub struct ClaimTokenIncentives<'info>{
    /// CHECK: Destination token-account authority and PDA seed.
    pub user:AccountInfo<'info>,
    #[account(init_if_needed,payer=payer,associated_token::mint=mint,associated_token::authority=user,associated_token::token_program=token_program)]
    pub user_ata:InterfaceAccount<'info,TokenAccount>,
    #[account(seeds=[b"global_volume_accumulator"],bump,has_one=mint @ PumpAmmError::InvalidIncentiveMint)]
    pub global_volume_accumulator:Account<'info,GlobalVolumeAccumulator>,
    #[account(mut,associated_token::mint=mint,associated_token::authority=global_volume_accumulator,associated_token::token_program=token_program)]
    pub global_incentive_token_account:InterfaceAccount<'info,TokenAccount>,
    #[account(mut,seeds=[b"user_volume_accumulator",user.key().as_ref()],bump)]
    pub user_volume_accumulator:Account<'info,UserVolumeAccumulator>,
    pub mint:InterfaceAccount<'info,Mint>,
    pub token_program:Interface<'info,TokenInterface>,
    pub system_program:Program<'info,System>,
    pub associated_token_program:Program<'info,AssociatedToken>,
    /// CHECK: Anchor event authority PDA.
    #[account(seeds=[b"__event_authority"],bump)]
    pub event_authority:AccountInfo<'info>,
    pub program:Program<'info,crate::program::PumpAmmRecovered>,
    #[account(mut)]pub payer:Signer<'info>,
}
pub fn claim(ctx:Context<ClaimTokenIncentives>)->Result<()> {
    let timestamp=Clock::get()?.unix_timestamp;
    let g=&ctx.accounts.global_volume_accumulator;
    let u=&mut ctx.accounts.user_volume_accumulator;
    u.user=ctx.accounts.user.key();
    reset(g,u,timestamp);
    // Recovered shared accumulator updater at original 0x6d408.
    let now_index=usize::try_from(timestamp).expect("SVM is 64-bit");
    let start_index=usize::try_from(g.start_time).expect("SVM is 64-bit");
    if now_index>=start_index && g.seconds_in_a_day!=0 {
        let period=usize::try_from(g.seconds_in_a_day).expect("SVM is 64-bit");
        let last=usize::try_from(u.last_update_timestamp).expect("SVM is 64-bit");
        let today=(now_index-start_index)/period;
        if last>=start_index {
            let previous_day=(last-start_index)/period;
            let end=usize::try_from(g.end_time).expect("SVM is 64-bit");
            let end_day=end.checked_sub(start_index).expect("end_time should be bigger than start_time")/period;
            if previous_day<today && previous_day<=end_day && g.sol_volumes[previous_day]>0 && u.current_sol_volume>0 {
                let reward=u64::try_from((u.current_sol_volume as u128)*(g.total_token_supply[previous_day] as u128)/(g.sol_volumes[previous_day] as u128)).map_err(|_|error!(PumpAmmError::Truncation))?;
                u.total_unclaimed_tokens=u.total_unclaimed_tokens.checked_add(reward).expect("Unexpected overflow");
                u.last_update_timestamp=timestamp;
                u.needs_claim=u.total_unclaimed_tokens>0;
                u.current_sol_volume=0;
            }
        }
        if timestamp<=g.end_time {
            // The original updater reads today's bucket even for a zero-volume claim.
            let _=g.sol_volumes[today];
            u.last_update_timestamp=timestamp;
            u.needs_claim=u.total_unclaimed_tokens>0 || u.current_sol_volume>0;
        }
    }
    let amount=u.total_unclaimed_tokens;
    if amount==0 {msg!("No tokens to claim");return Ok(());}
    let bump=[ctx.bumps.global_volume_accumulator];let signer:&[&[u8]]=&[b"global_volume_accumulator",&bump];
    require!(ctx.accounts.global_incentive_token_account.key()!=ctx.accounts.user_ata.key() || ctx.accounts.global_incentive_token_account.owner==g.key(),PumpAmmError::SelfTransferNotAllowed);
    token_interface::transfer_checked(CpiContext::new_with_signer(ctx.accounts.token_program.to_account_info(),TransferChecked{from:ctx.accounts.global_incentive_token_account.to_account_info(),mint:ctx.accounts.mint.to_account_info(),to:ctx.accounts.user_ata.to_account_info(),authority:g.to_account_info()},&[signer]),amount,ctx.accounts.mint.decimals)?;
    let total_claimed_tokens=u.total_claimed_tokens+amount;
    u.total_unclaimed_tokens=0;u.total_claimed_tokens=total_claimed_tokens;u.has_total_claimed_tokens=true;u.needs_claim=u.current_sol_volume>0;u.last_update_timestamp=timestamp;
    let event=ClaimTokenIncentivesEvent{user:ctx.accounts.user.key(),mint:ctx.accounts.mint.key(),amount,timestamp,total_claimed_tokens:u.total_claimed_tokens,current_sol_volume:u.current_sol_volume};emit!(event.clone());emit_cpi!(event);
    Ok(())
}
#[event]
#[derive(Clone)]
pub struct SyncUserVolumeAccumulatorEvent{pub user:Pubkey,pub total_claimed_tokens_before:u64,pub total_claimed_tokens_after:u64,pub timestamp:i64}
#[event]
#[derive(Clone)]
pub struct AdminUpdateTokenIncentivesEvent{pub start_time:i64,pub end_time:i64,pub day_number:u64,pub token_supply_per_day:u64,pub mint:Pubkey,pub seconds_in_a_day:i64,pub timestamp:i64}
#[event]
#[derive(Clone)]
pub struct ClaimTokenIncentivesEvent{pub user:Pubkey,pub mint:Pubkey,pub amount:u64,pub timestamp:i64,pub total_claimed_tokens:u64,pub current_sol_volume:u64}
