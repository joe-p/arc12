# Functionality Overview

## Opt-In

If intended receiver does not have a vault:
1. Call `create_vault` on master
   1. Cost includes MBR of vault app and box in master
2. Call `opt_in` on vault
   1. Cost includes box in vault app and ASA MBR
3. Transfer ASA to vault

If intended receiver does have a vault, but it isn't opted in to the ASA:
1. Call `opt_in` on vault
   1. Cost includes box in vault app and ASA MBR
2. Transfer ASA to vault

If intended receiver does have a vault and it is opted into ASA
1. Transfer ASA to vault

## Claim

This functionality assumes the claimer is already opted into the ASA. This *can* be done atomically with the claim function, but is not required.

If there will be other assets remaining in the vault after the claim:
1. Call `claim` on vault
   1. ASA MBR and box MBR is returned to the account who opted the vault into the ASA

If the asset being claimed is the last asset in the vault:
1. Call `claim` on vault
   1. ASA MBR and box MBR is returned to the account who opted the vault into the ASA
2. In an atomic transaction with claim, call `delete_vault` on master app.
   1. Vault app MBR and master box MBR will be returned to the account who created the vault


## Reject

If there will be other assets remaining in the vault after the claim:
1. Call `reject` on vault
   1. All fees will be refunded to the claimer
   2. Remaining balance from MBR will be sent to fee sink

If the asset being claimed is the last asset in the vault:
1. Call `reject` on vault
   1. All fees will be refunded to the claimer
   2. Remaining balance from MBR will be sent to fee sink
2. In an atomic transaction with claim, call `delete_vault` on master app.
   1. Vault app MBR and master box MBR will be returned to the account who created the vault


# Running Tests

1. `python -v venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r tests/requirements.txt`
4. `pytest tests/`

# Generating TEALrb Output

1. Install Ruby 2.7+ if not already installed
2. `bundle install`
3. `bundle exec ruby arc12.rb`