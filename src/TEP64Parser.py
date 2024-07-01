import requests
from hashlib import sha256
from pytoniq_core import Cell


class ContentParsingError(Exception):
    """Base exception class for content parsing errors."""

    pass


class InvalidPrefixError(ContentParsingError):
    """Exception raised for invalid prefix errors during parsing."""

    pass


class DataFetchingError(ContentParsingError):
    """Exception raised for errors during data fetching."""

    pass


class TEP64Parser:
    """
    A parser for TEP-64 token data.

    Attributes:
        ipfs_endpoint (str): The base URL for fetching IPFS data.
        prefix_handlers (dict): Custom handlers for specific prefix values.
        extra_default_values (dict): Additional default values for onchain content.
        default_handlers (dict): Default handlers for predefined prefixes.
    """

    def __init__(
        self,
        ipfs_endpoint="https://ipfs.io/ipfs/",
        prefix_handlers=None,
        extra_default_values=None,
    ):
        """
        Initialize TEP64Parser with optional parameters.

        Args:
            ipfs_endpoint (str, optional): The base URL for IPFS data fetching. Defaults to "https://ipfs.io/ipfs/".
            prefix_handlers (dict, optional): Custom handlers for specific prefix values. Defaults to None.
            extra_default_values (dict, optional): Additional default values for onchain content. Defaults to None.
        """
        self.ipfs_endpoint = ipfs_endpoint
        self.prefix_handlers = prefix_handlers or {}
        self.extra_default_values = extra_default_values or {}
        self.default_handlers = {
            0x01: self.default_handle_offchain_content,
            0x00: self.default_handle_onchain_content,
        }

    def fetch_data(self, uri):
        """
        Fetch data from a given URI.

        Args:
            uri (str): The URI to fetch data from.

        Returns:
            str: The fetched data.

        Raises:
            DataFetchingError: If there's an error fetching the data.
        """
        try:
            if uri.startswith("ipfs://"):
                ipfs_uri = uri.replace("ipfs://", self.ipfs_endpoint)
                response = requests.get(ipfs_uri)
            else:
                response = requests.get(uri)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            raise DataFetchingError(f"Error fetching data: {e}")

    @staticmethod
    def parse_prefix(cs):
        """
        Parse the prefix value from a Cell.

        Args:
            cs (Cell): The Cell object containing the data to parse.

        Returns:
            int: The parsed prefix value as an integer.
        """
        prefix = cs.load_bits(8)
        return int(prefix.to01())

    def default_handle_offchain_content(self, cs):
        """
        Handle offchain content parsing and data fetching.

        Args:
            cs (Cell): The Cell object containing the offchain content.

        Returns:
            dict: Parsed offchain content data.

        Raises:
            InvalidPrefixError: If the prefix value is invalid for offchain content.
            DataFetchingError: If there's an error fetching the data.
        """
        uri = None

        if cs.refs == 0:
            prefix_value = self.parse_prefix(cs)
            if prefix_value != 0x00:
                raise InvalidPrefixError(
                    f"Invalid prefix for offchain content: {prefix_value}"
                )
            uri = cs.load_string(cs.bits)
        else:
            uri = cs.load_snake_string()

        data = self.fetch_data(uri)
        return {"type": "offchain", "uri": uri, "data": data}

    @staticmethod
    def load_metadata(cs):
        """
        Load metadata from a Cell.

        Args:
            cs (Cell): The Cell object containing the metadata.

        Returns:
            dict: Loaded metadata as a dictionary.
        """
        return cs.load_dict(256)

    @staticmethod
    def calculate_key(key_string):
        """
        Calculate a key using SHA-256 from a given string.

        Args:
            key_string (str): The string to calculate the key from.

        Returns:
            int: The calculated key as an integer.
        """
        key_bytes = sha256(key_string.encode("utf-8")).digest()
        return int.from_bytes(key_bytes, "big")

    def default_handle_onchain_content(self, cs):
        """
        Handle onchain content parsing and metadata loading.

        Args:
            cs (Cell): The Cell object containing the onchain content.

        Returns:
            dict: Parsed onchain content metadata.

        """
        default_values = {
            "uri": None,
            "name": None,
            "description": None,
            "image": None,
            "image_data": None,
            "symbol": None,
            "decimals": "9",
            "amount_style": "n",
            "render_type": "currency",
        }

        default_values.update(self.extra_default_values)

        metadata_keys = {label: self.calculate_key(label) for label in default_values}
        metadata = self.load_metadata(cs)
        all_metadata = default_values.copy()

        for label, key in metadata_keys.items():
            value_chunk = metadata.get(key)
            if value_chunk is not None:
                value = value_chunk.load_snake_string()
                all_metadata[label] = value

        return {"type": "onchain", "metadata": all_metadata}

    def parse_content(self, content: Cell):
        """
        Parse content based on the prefix value.

        Args:
            content (Cell): The Cell object containing the content to parse.

        Returns:
            dict: Parsed content data.

        Raises:
            InvalidPrefixError: If the prefix value is invalid.
        """
        cs = content.begin_parse()
        prefix_value = self.parse_prefix(cs)

        # Merge custom handlers with default handlers, with custom handlers taking precedence
        handlers = {**self.default_handlers, **self.prefix_handlers}

        # Fetch the appropriate handler for the given prefix
        handler = handlers.get(prefix_value)

        if handler:
            return handler(cs)
        else:
            raise InvalidPrefixError(f"Invalid prefix: {prefix_value}")


# Example custom handler for a new prefix
def custom_prefix_handler(cs, ipfs_endpoint):
    """
    Custom handler for a specific prefix.

    Args:
        cs (Cell): The Cell object containing the data to handle.
        ipfs_endpoint (str): The IPFS endpoint URL.

    Returns:
        dict: Custom handler result data.
    """
    # Custom logic for handling this prefix
    return {"type": "custom", "data": "custom handler logic"}


# Register custom handlers
custom_handlers = {
    0x02: custom_prefix_handler,
    # Add more custom handlers as needed
}

# Create an instance of the parser with custom handlers
parser = TEP64Parser(
    prefix_handlers=custom_handlers,
)

# Load the jetton content from BOC strings
offchain_jetton_content = Cell.one_from_boc(
    "b5ee9c7201010101004500008601697066733a2f2f6261666b7265696173743466716c6b7034757079753263766f37666e376161626a757378373635797a767169747372347270776676686a67756879"
)  # https://tonviewer.com/EQD0vdSA_NedR9uvbgN9EikRX-suesDxGeFg69XQMavfLqIw
onchain_jetton_content = Cell.one_from_boc(
    "b5ee9c7201020c0100012f00010300c00102012002030143bff082eb663b57a00192f4a6ac467288df2dfeddb9da1bee28f6521c8bebd21f1ec0040201200506006e0068747470733a2f2f626974636f696e636173682d6578616d706c652e6769746875622e696f2f776562736974652f6c6f676f2e706e6702012007080142bf89046f7a37ad0ea7cee73355984fa5428982f8b37c8f7bcec91f7ac71a7cd1040b0141bf4546a6ffe1b79cfdd86bad3db874313dcde2fb05e6a74aa7f3552d9617c79d13090141bf6ed4f942a7848ce2cb066b77a1128c6a1ff8c43f438a2dce24612ba9ffab8b030a0016005061626c6f636f696e200008005062630078004c6f772066656520706565722d746f2d7065657220656c656374726f6e6963206361736820616c7465726e617469766520746f20426974636f696e"
)  # https://tonviewer.com/EQA4pCk0yK-JCwFD4Nl5ZE4pmlg4DkK-1Ou4HAUQ6RObZNMi
offchain_collection_content = Cell.one_from_boc(
    "b5ee9c7201010101002800004c0168747470733a2f2f6e66742e667261676d656e742e636f6d2f6e756d626572732e6a736f6e"
)  # https://tonviewer.com/EQD7Qtnas8qpMvT7-Z634_6G60DGp02owte5NnEjaWq6hb7v
offchain_individual_content = Cell.one_from_boc(
    "b5ee9c720101010100330000620168747470733a2f2f6e66742e667261676d656e742e636f6d2f6e756d6265722f38383830393639373530322e6a736f6e"
)  # https://tonviewer.com/EQD7Qtnas8qpMvT7-Z634_6G60DGp02owte5NnEjaWq6hb7v

try:
    offchain_jetton_content_result = parser.parse_content(offchain_jetton_content)
    print("offchain_jetton_content_result=", offchain_jetton_content_result)

    onchain_jetton_content_result = parser.parse_content(onchain_jetton_content)
    print("onchain_jetton_content_result=", onchain_jetton_content_result)

    offchain_collection_content_result = parser.parse_content(
        offchain_collection_content
    )
    print("offchain_collection_content_result=", offchain_collection_content_result)

    offchain_individual_content_result = parser.parse_content(
        offchain_individual_content
    )
    print("offchain_individual_content_result=", offchain_individual_content_result)
except ContentParsingError as e:
    print(f"Error during content parsing: {e}")
