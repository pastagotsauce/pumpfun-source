use anchor_lang::prelude::*;
use crate::PumpAmmError;
use super::GlobalConfig;

impl GlobalConfig {
    pub(crate) fn set_lp_fee_basis_points(&mut self, fee: u64) -> Result<()> {
        require_gte!(1000u64, fee, PumpAmmError::FeeBasisPointsExceedsMaximum);
        self.lp_fee_basis_points = fee;
        Ok(())
    }

    pub(crate) fn set_protocol_fee_basis_points(&mut self, fee: u64) -> Result<()> {
        require_gte!(1000u64, fee, PumpAmmError::FeeBasisPointsExceedsMaximum);
        self.protocol_fee_basis_points = fee;
        Ok(())
    }

    pub(crate) fn set_coin_creator_fee_basis_points(&mut self, fee: u64) -> Result<()> {
        require_gte!(1000u64, fee, PumpAmmError::FeeBasisPointsExceedsMaximum);
        self.coin_creator_fee_basis_points = fee;
        Ok(())
    }

    pub(crate) fn set_protocol_fee_recipients(&mut self, recipients: [Pubkey; 8]) -> Result<()> {
        require!(recipients.iter().all(|key| *key != Pubkey::default()),
            PumpAmmError::AllProtocolFeeRecipientsShouldBeNonZero);
        require!(recipients.windows(2).all(|pair| pair[0] < pair[1]),
            PumpAmmError::UnsortedNotUniqueProtocolFeeRecipients);
        self.protocol_fee_recipients = recipients;
        Ok(())
    }
}
