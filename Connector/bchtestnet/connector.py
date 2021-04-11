RPC_CORE_HOST = "bitcoincore"
RPC_CORE_PORT = 8332
RPC_CORE_USER = "swapper"
RPC_CORE_PASSWORD = "swapper"

RPC_ELECTRUM_CASH_HOST = "electrum"
RPC_ELECTRUM_CASH_PORT = 30000
RPC_ELECTRUM_CASH_USER = "swapper"
RPC_ELECTRUM_CASH_PASSWORD = "swapper"

RPC_CORE_ENDPOINT = 'http://{}:{}@{}:{}'.format(RPC_CORE_USER, RPC_CORE_PASSWORD, RPC_CORE_HOST, RPC_CORE_PORT)
RPC_ELECTRUM_CASH_ENDPOINT = 'http://{}:{}@{}:{}'.format(RPC_ELECTRUM_CASH_USER, RPC_ELECTRUM_CASH_PASSWORD, RPC_ELECTRUM_CASH_HOST, RPC_ELECTRUM_CASH_PORT)