import time
import random
from web3 import Web3
import json
from termcolor import colored
import os
import requests
from web3.middleware import geth_poa_middleware
from web3.middleware import latest_block_based_cache_middleware

RPC = "https://rpc.ankr.com/polygon"
web3 = Web3(Web3.HTTPProvider(RPC))
web3_instance = Web3(Web3.HTTPProvider(RPC))

web3.middleware_onion.inject(geth_poa_middleware, layer=0)
web3.middleware_onion.inject(latest_block_based_cache_middleware, layer=0)

STG_contract_address = "0x2f6f07cdcf3588944bf4c42ac74ff24bf56e7590"
Lock_contract = "0x3AB2DA31bBD886A7eDF68a6b60D3CDe657D3A15D"

# Загрузка ABI из файлов
with open('STG_abi.json', 'r') as file:
    stg_abi = json.load(file)
with open('lock_abi.json', 'r') as file:
    lock_abi = json.load(file)

def get_current_gas_price_polygon(web3_instance):
    try:
        # Получение текущей рекомендуемой цены газа с сети Polygon
        current_gas_price = web3_instance.eth.gas_price
        return current_gas_price
    except Exception as e:
        print(f"Ошибка при получении цены газа: {e}")
        return None


def convert_to_ether_format(amount, web3_instance):
    return web3_instance.to_wei(amount, 'ether')

def load_abi_from_file(file_path):
    with open(file_path, 'r') as f:
        STG_abi = json.load(f)
        return STG_abi

def gas_price():
    gas_price_wei = get_current_gas_price_polygon(web3)
    return gas_price_wei

def get_current_gas_limit():
    latest_block = web3.eth.get_block("latest")
    return latest_block["gasLimit"]

RETRY_SWAPS = 5

def intToDecimal(qty, decimal):
    return int(qty * 10 ** decimal)
def to_checksum_address(address):
    return web3.to_checksum_address(address)

def get_0x_quote(network: str, from_token: str, to_token: str, value: int, slippage: float):
    try:
        url_chains = {
            "Polygon": "polygon.",
        }

        api_key = os.getenv("0X_API_KEY")
        headers = {'0x-api-key': 'YOUR 0X api'}

        url = f"https://{url_chains[network]}api.0x.org/swap/v1/quote?buyToken={to_token}&sellToken={from_token}&sellAmount={value}&slippagePercentage={slippage / 100}"

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            result = [response.json()]
            return result
        else:
            print(f"Ошибка: response.status_code = {response.status_code}")
            return False
    except Exception as error:
        print(f"Ошибка в 'get_0x_quote()': {error}")
        return False


def zeroX_swap(network: str, private_key: str, _amount: float, retry=0):
    while True:
        try:
            address = web3.eth.account.from_key(private_key).address
            checksum_address = web3.to_checksum_address(address)
            nonce = web3.eth.get_transaction_count(checksum_address)

            from_token = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
            to_token = STG_contract_address
            amount = convert_to_ether_format(_amount, web3)

            json_data = get_0x_quote(network, from_token, to_token, amount, 1)

            if json_data is not False and isinstance(json_data, list) and len(json_data) > 0:
                spender = json_data[0]["allowanceTarget"]
            else:
                print("Не удалось получить данные для свапа.")
                return None

            tx = {
                "from": checksum_address,
                "nonce": nonce,
                "gas": 500000,
                "to": web3.to_checksum_address(json_data[0]["to"]),
                "data": json_data[0]["data"],
                "value": int(json_data[0]["value"]),
                "chainId": web3.eth.chain_id,
            }

            tx['gasPrice'] = web3.eth.gas_price
            signed_tx = web3.eth.account.sign_transaction(tx, private_key)
            tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Отправка транзакции свапа...")

            if check_status_tx(web3, tx_hash):
                print(f"Транзакция свапа подтверждена: https://polygonscan.com/tx/{tx_hash.hex()}")
                time.sleep(random.randint(30, 60))  # Задержка после свапа
                return tx_hash
            else:
                retry += 1
                if retry > RETRY_SWAPS:
                    return None
                time.sleep(random.randint(10, 15))

        except Exception as e:
            retry += 1
            if retry > RETRY_SWAPS:
                return None
            time.sleep(random.randint(10, 15))

        return None

def check_status_tx(web3_instance, tx_hash, max_retries=10):
    retries = 0
    while retries < max_retries:
        try:
            receipt = web3_instance.eth.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return receipt.status == 1
            else:
                time.sleep(10)
                retries += 1
        except Exception as e:

            time.sleep(20)
            retries += 1

    return False

def get_transaction_receipt(web3_instance, tx_hash, max_retries=10, wait_interval=20):
    retries = 0
    while retries < max_retries:
        try:
            tx_receipt = web3_instance.eth.get_transaction_receipt(tx_hash)
            if tx_receipt is not None:
                if tx_receipt.status == 1:
                    return True  # Возвращает True, если транзакция успешно подтверждена
                else:
                    print(f"Транзакция не удалась: https://polygonscan.com/tx/{tx_hash.hex()}")
                    return False
            else:
                time.sleep(wait_interval)
                retries += 1
        except Exception as e:
            retries += 1
            time.sleep(wait_interval)

    print(f"Не удалось подтвердить транзакцию после {max_retries} попыток: {tx_hash.hex()}")
    return False

def set_max_approval(token_contract_address, spender_address, private_key):
    # Загрузка ABI контракта STG
    with open('STG_abi.json', 'r') as abi_file:
        token_abi = json.load(abi_file)

    token_contract = web3.eth.contract(address=token_contract_address, abi=token_abi)
    wallet_address = web3.eth.account.from_key(private_key).address
    nonce = web3.eth.get_transaction_count(wallet_address)

    max_allowance = 2**256 - 1  # Максимальное число для approval

    approve_txn = token_contract.functions.approve(spender_address, max_allowance).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': 500000,
        'gasPrice': get_current_gas_price_polygon(web3)
    })

    signed_txn = web3.eth.account.sign_transaction(approve_txn, private_key=private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)

    # Добавление проверки статуса транзакции
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 1:
        print(f"Транзакция одобрения успешно выполнена: https://polygonscan.com/tx/{tx_hash.hex()}")
        return True
    else:
        print(f"Ошибка при выполнении транзакции одобрения: https://polygonscan.com/tx/{tx_hash.hex()}")
        return False

def approve(private_key, spender, amount):
    try:
        wallet_address = web3.eth.account.from_key(private_key).address
        wallet = to_checksum_address(wallet_address)
        STG_abi = load_abi_from_file('STG_abi.json')
        token = to_checksum_address(STG_contract_address)
        contract = web3.eth.contract(address=token, abi=STG_abi)
        decimals = 18
        amount_in_wei = int(amount * 10 ** decimals)

        spender_address = to_checksum_address(spender)
        nonce = web3.eth.get_transaction_count(wallet_address)
        gas_price_wei = gas_price()
        gas_limit = get_current_gas_limit()
        tx = {
            'nonce': nonce,
            'from': wallet,
            'gasPrice': gas_price_wei,
            'gas': 500000,
            'chainId': 137,
            'value': 0,
        }

        contract_txn = contract.functions.approve(spender_address, amount_in_wei).build_transaction(tx)
        signed_txn = web3.eth.account.sign_transaction(contract_txn, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        time.sleep(10)

        # Проверка статуса транзакции
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            tx_link = f"https://polygonscan.com/tx/{tx_hash.hex()}"
            print(f"Транзакция approve выполнена успешно: https://polygonscan.com/tx/{tx_link}")
            return True
        else:
            print("Ошибка при выполнении транзакции approve.")
            return False

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

max_retries = 5

def token_allowance(token_contract_address, spender_address, private_key):
    wallet_address = web3.eth.account.from_key(private_key).address
    token_contract = web3.eth.contract(address=Web3.to_checksum_address(token_contract_address), abi=load_abi_from_file('STG_abi.json'))
    allowance = token_contract.functions.allowance(wallet_address, spender_address).call()
    return allowance

def get_balance(private_key):
    wallet_address = web3.eth.account.from_key(private_key).address
    STG_abi = load_abi_from_file('STG_abi.json')
    checksum_address = to_checksum_address(STG_contract_address)
    contract = web3.eth.contract(address=checksum_address, abi=STG_abi)
    token_balance = contract.functions.balanceOf(wallet_address).call()
    decimals = 18
    STG_balance = token_balance / 10 ** decimals
    return STG_balance

def get_transaction_receipt(web3_instance, tx_hash, max_retries=10, wait_interval=20):
    retries = 0
    while retries < max_retries:
        try:
            tx_receipt = web3_instance.eth.get_transaction_receipt(tx_hash)
            if tx_receipt is not None:
                if tx_receipt.status == 1:
                    # Успешное выполнение транзакции
                    #print(f"Транзакция подтверждена: https://polygonscan.com/tx/{tx_hash.hex()}")
                    return True
                else:
                    # Транзакция не удалась
                    print(f"Транзакция не удалась: https://polygonscan.com/tx/{tx_hash.hex()}")
                    return False
            else:
                time.sleep(wait_interval)
                retries += 1
        except Exception as e:
            # Удаление строки об ошибке
            retries += 1
            time.sleep(wait_interval)

    print(f"Не удалось подтвердить транзакцию после {max_retries} попыток: {tx_hash.hex()}")
    return False

def wait_for_low_gas_price():
    while True:
        current_gas_price = gas_price()
        gas_price_gwei = current_gas_price / 10 ** 9
        print(f"Current gas price: {gas_price_gwei}")

        if gas_price_gwei <= 200:  #Выбор лимита газа
            break  # Выходим из цикла, если gas_price_gwei опустилось ниже 200
        else:
            print("Gas price is too high. Waiting for 30 seconds...")
            time.sleep(30)

wait_for_low_gas_price()

def create_lock(private_key, value, unlock_time):
    try:
        wallet_address = web3.eth.account.from_key(private_key).address
        wallet = to_checksum_address(wallet_address)
        Lock_abi = load_abi_from_file('lock_abi.json')

        contract_address = to_checksum_address(Lock_contract)
        contract = web3.eth.contract(address=contract_address, abi=Lock_abi)
        decimals = 18
        amount = web3.from_wei(get_balance(private_key), 'ether')
        nonce = web3.eth.get_transaction_count(wallet_address)
        value = int(value * 0.99)

        current_gas_price = get_current_gas_price_polygon(web3)
        increased_gas_price = int(current_gas_price * 1.1)

        tx = {
            'nonce': nonce,  
            'from': wallet,
            'gasPrice': increased_gas_price,
            'gas': 600000,
            'chainId': 137,
            'value': 0,
        }

        contract_txn = contract.functions.create_lock(value, unlock_time).build_transaction(tx)
        signed_txn = web3.eth.account.sign_transaction(contract_txn, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print("Создание lock транзакции...")

        if get_transaction_receipt(web3, tx_hash):
            print(f"Транзакция lock подтверждена: https://polygonscan.com/tx/{tx_hash.hex()}")
        else:
            print(f"Ошибка при создании lock: https://polygonscan.com/tx/{tx_hash.hex()}")

        return get_transaction_receipt(web3, tx_hash)

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

def set_allowance(private_key, spender, amount, token_address, token_abi):
    try:
        spender_address = Web3.to_checksum_address(spender)  # Преобразование в checksum формат
        wallet_address = Web3.to_checksum_address(web3.eth.account.from_key(private_key).address)
        token_contract = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=token_abi)

        approve_txn = token_contract.functions.approve(spender_address, amount).build_transaction({
            'from': wallet_address,
            'nonce': web3.eth.get_transaction_count(wallet_address)
        })

        signed_txn = web3.eth.account.sign_transaction(approve_txn, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print(f"Транзакция разрешения отправлена, хеш: https://polygonscan.com/tx/{tx_hash.hex()}")
        return tx_hash
    except Exception as e:
        print(f"Ошибка в 'set_allowance()': {e}")
        return None


if __name__ == "__main__":
    with open("private_keys.txt", "r") as f:
        private_keys_list = [row.strip() for row in f]

    total_wallets = len(private_keys_list)
    processed_wallets = 0
    successful_transactions = []  # Список для хранения успешных транзакций

    
    with open('STG_abi.json', 'r') as file:
        stg_abi = json.load(file)
    with open('lock_abi.json', 'r') as file:
        Lock_abi = json.load(file)

    for private_key in private_keys_list:
        processed_wallets += 1
        wallet_address = web3.eth.account.from_key(private_key).address

        print(colored(f"Обработка кошелька {wallet_address} ({processed_wallets} из {total_wallets})", "yellow"))

        STG_balance = get_balance(private_key)  # Получение баланса STG для текущего кошелька

        if STG_balance < 0.5:
            # Если баланс STG меньше 0.5, то выполнить свап
            min_swap_amount = 0.65  # Минимальное значение для свапа
            max_swap_amount = 0.8  # Максимальное значение для свапа
            swap_amount = random.uniform(min_swap_amount, max_swap_amount)
            swap_tx_hash = zeroX_swap("Polygon", private_key, swap_amount)  # Получаем хэш транзакции свапа
            time.sleep(random.randint(20, 40))
            if swap_tx_hash:
                # Ожидание подтверждения транзакции свапа
                for _ in range(max_retries):
                    tx_receipt = web3.eth.get_transaction_receipt(swap_tx_hash)

                    if tx_receipt is not None:
                        # Транзакция свапа подтверждена, выход из цикла
                        successful_transactions.append(swap_tx_hash)
                        #print(colored("Транзакция свапа подтверждена", "green"))
                        break
                    else:
                        # Транзакция свапа ещё не подтверждена, ждем
                        time.sleep(retry_interval)
                        print(colored("Транзакция свапа ещё не подтверждена", "red"))

        # Обновляем баланс STG после свапа
        STG_balance = get_balance(private_key)
        time.sleep(random.randint(10, 20))
        # Установка разрешения на передачу токенов перед стейкингом
        spender_address = "0x3AB2DA31bBD886A7eDF68a6b60D3CDe657D3A15D"
        staking_allowance = intToDecimal(STG_balance, 18)

        # Approve spending of STG tokens
        amount_to_approve = STG_balance
        approve(private_key, spender_address, amount_to_approve)

        # Ждем подтверждения разрешения
        #print(f"Ожидание подтверждения разрешения ...")
        #time.sleep(10)

        # Выполнение стейкинга
        value = intToDecimal(STG_balance, 18)
        unlock_time = 1783748761
        create_lock(private_key, value, unlock_time)
        time.sleep(random.randint(10, 20))

    print(colored("Все транзакции успешно завершены.", "green"))
