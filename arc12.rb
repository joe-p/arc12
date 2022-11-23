# frozen_string_literal: true

require 'tealrb'

class Vault < TEALrb::Contract
  @version = 8

  # @subroutine
  # @param vault_creator [Account]
  def close_acct(vault_creator)
    assert vault_creator == global['creator']

    inner_txn.begin
    inner_txn.type_enum = txn_type.pay
    inner_txn.receiver = vault_creator
    inner_txn.amount = global.current_application_address.min_balance
    inner_txn.fee = 0
    inner_txn.close_remainder_to = this_txn.sender
    inner_txn.submit

    $delete_vault_txn = group_txns[this_txn.group_index + 1]
    assert $delete_vault_txn.application_id == global['master']
  end

  # @abi
  # @create
  # Method called for creation of the vault
  # @param receiver [Account] The account that can claim ASAs from this vault
  # @param sender [Account]
  def create(receiver, sender)
    global['creator'] = sender
    global['receiver'] = receiver
    global['master'] = global.caller_application_id
  end

  # @abi
  # @param asa_creator [Account]
  # @param fee_sink [Account]
  # @param asa [Asset]
  # @param vault_creator [Account]
  def reject(asa_creator, fee_sink, asa, vault_creator)
    vault_creator = asa_creator if vault_creator == global.zero_address
    assert this_txn.sender == global['receiver']
    assert fee_sink == addr('Y76M3MSY6DKBRHBL7C3NNDXGS5IIMQVQVUAB6MP4XEMMGVF2QWNPL226CA')
    $pre_mbr = global.current_application_address.min_balance
    $pre_fee = global.current_application_address.balance

    # send ASA to creator
    inner_txn.begin
    inner_txn.type_enum = txn_type.asset_transfer
    inner_txn.asset_receiver = asa_creator
    inner_txn.xfer_asset = asa
    inner_txn.asset_close_to = asa_creator
    inner_txn.fee = global.min_txn_fee
    inner_txn.submit

    box_del itob asa

    $fee_amt = $pre_fee - global.current_application_address.balance
    $mbr_amt = $pre_mbr - global.current_application_address.min_balance

    # send MBR to fee sink
    inner_txn.begin
    inner_txn.type_enum = txn_type.pay
    inner_txn.receiver = fee_sink
    inner_txn.amount = $mbr_amt - (2 * $fee_amt)
    inner_txn.fee = global.min_txn_fee
    inner_txn.submit

    close_acct(vault_creator) if global.current_application_address.assets == 0
  end

  # @abi
  # Opts into the given asa
  # @param asa [Asset] The asset to opt-in to
  # @param mbr_payment [Pay] The payment to cover this contracts MBR
  def opt_in(asa, mbr_payment)
    $asa_bytes = itob(asa)
    assert !box_exists?($asa_bytes)
    assert mbr_payment.sender == this_txn.sender
    assert mbr_payment.receiver == global.current_application_address

    $pre_mbr = global.current_application_address.min_balance

    box_create($asa_bytes, 32)
    box[$asa_bytes] = this_txn.sender

    # // Opt into ASA
    inner_txn.begin
    inner_txn.type_enum = txn_type.asset_transfer
    inner_txn.asset_receiver = global.current_application_address
    inner_txn.asset_amount = 0
    inner_txn.fee = 0
    inner_txn.xfer_asset = asa
    inner_txn.submit

    assert mbr_payment.amount == global.current_application_address.min_balance - $pre_mbr
  end

  # @abi
  # @on_completion [DeleteApplication]
  def delete
    assert global.current_application_address.balance == 0
    assert this_txn.sender == global.creator_address
  end

  # @abi
  # Sends the ASA to the intended receiver
  # @param asa [Asset] The ASA to send
  # @param creator [Account] The account that funded the MBR for the application
  # @param asa_mbr_funder [Account] The account that funded the MBR for the ASA
  def claim(asa, creator, asa_mbr_funder)
    $asa_bytes = itob(asa)

    asa_mbr_funder = creator if asa_mbr_funder == global.zero_address

    assert box_exists?($asa_bytes)
    assert asa_mbr_funder == box[$asa_bytes]
    assert this_txn.sender == global['receiver']
    assert creator == global['creator']

    $initial_mbr = global.current_application_address.min_balance

    box_del $asa_bytes

    # // Close ASA to receiver
    inner_txn.begin
    inner_txn.type_enum = txn_type.asset_transfer
    inner_txn.asset_receiver = this_txn.sender
    inner_txn.fee = 0
    inner_txn.asset_amount = global.current_application_address.asset_balance(asa)
    inner_txn.xfer_asset = asa
    inner_txn.asset_close_to = this_txn.sender
    inner_txn.submit

    # // Send ASA MBR to funder
    inner_txn.begin
    inner_txn.type_enum = txn_type.pay
    inner_txn.receiver = asa_mbr_funder
    inner_txn.amount = $initial_mbr - global.current_application_address.min_balance
    inner_txn.fee = 0
    inner_txn.submit

    close_acct(creator) if global.current_application_address.assets == 0
  end
end

class Master < TEALrb::Contract
  @version = 8

  # @abi
  # @create
  def create
    approve
  end

  # @abi
  # Create Vault
  # @param receiver [Account]
  # @param mbr_payment [Pay]
  # @return [Uint64] Application ID of the vault for receiver
  def create_vault(receiver, mbr_payment)
    assert !box_exists?(receiver)
    assert mbr_payment.receiver == global.current_application_address
    assert mbr_payment.sender == this_txn.sender
    assert mbr_payment.close_remainder_to == global.zero_address

    $pre_create_mbr = global.current_application_address.min_balance

    # // Create vault
    inner_txn.begin
    inner_txn.type_enum = txn_type.application_call
    inner_txn.application_id = 0
    inner_txn.approval_program = byte_b64 Vault.new.compiled_program
    inner_txn.clear_state_program = apps[0].clear_state_program
    inner_txn.on_completion = int('NoOp')
    inner_txn.accounts = receiver
    inner_txn.accounts = this_txn.sender
    inner_txn.fee = 0
    inner_txn.application_args = method_signature('create(account,account)void')
    inner_txn.global_num_byte_slice = 2
    inner_txn.global_num_uint = 1
    inner_txn.submit

    $vault_id = inner_txn.created_application_id

    # // Fund vault with account MBR
    inner_txn.begin
    inner_txn.type_enum = txn_type.pay
    inner_txn.receiver = $vault_id.address
    inner_txn.amount = global.min_balance
    inner_txn.fee = 0
    inner_txn.submit

    box_create receiver, 8
    box[receiver] = itob $vault_id

    assert mbr_payment.amount == (global.current_application_address.min_balance - $pre_create_mbr) + global.min_balance

    return itob $vault_id
  end

  # @abi
  # @param receiver [Account]
  # @param vault_axfer [Axfer]
  # @param vault [Application]
  def verify_axfer(receiver, vault_axfer, vault)
    assert box_exists?(receiver)

    assert btoi(box[receiver]) == vault
    assert vault_axfer.asset_receiver == vault.address
    assert vault_axfer.close_remainder_to == global.zero_address
  end

  # @abi
  # @param receiver [Account]
  # @return [Uint64] Application ID of the vault for receiver
  def get_vault_id(receiver)
    assert box_exists?(receiver)
    return box[receiver]
  end

  # @abi
  # @param receiver [Account]
  # @return [Address] Address of the vault for receiver
  def get_vault_addr(receiver)
    assert box_exists?(receiver)
    return app(btoi(box[receiver])).address
  end

  # @abi
  # @param vault [Application]
  # @param creator [Account]
  def delete_vault(vault, creator)
    assert vault == btoi(box[this_txn.sender])
    $vault_creator = vault.global_value('creator')
    assert $vault_creator == creator

    $pre_delete_mbr = global.current_application_address.min_balance

    # // Delete vault
    inner_txn.begin
    inner_txn.type_enum = txn_type.application_call
    inner_txn.application_id = btoi(box[this_txn.sender])
    inner_txn.on_completion = int('DeleteApplication')
    inner_txn.application_args = method_signature('delete()void')
    inner_txn.accounts = creator
    inner_txn.fee = 0
    inner_txn.submit

    box_del this_txn.sender

    # // Send vault MBR to creator
    inner_txn.begin
    inner_txn.type_enum = txn_type.pay
    inner_txn.receiver = $vault_creator
    inner_txn.amount = $pre_delete_mbr - global.current_application_address.min_balance
    inner_txn.fee = 0
    inner_txn.submit
  end
end

Vault.new.dump
Master.new.dump
