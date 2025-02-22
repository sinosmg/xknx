"""Implementation of Basic KNX datatypes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from inspect import isabstract
from typing import Any, Generic, TypedDict, TypeVar, cast

from xknx.exceptions import ConversionError, CouldNotParseTelegram

from .payload import DPTArray, DPTBinary

T = TypeVar("T", bound=type["DPTBase"])  # pylint: disable=invalid-name
TComplexData = TypeVar("TComplexData", bound="DPTComplexData")  # pylint: disable=invalid-name


class _DPTMainSubDict(TypedDict):
    """DPT type dictionary in accordance to xknxproject DPTType data."""

    main: int
    sub: int | None


class DPTBase(ABC):
    """
    Base class for KNX data point type transcoder.

    KNX communicates using Group-addresses, and every Group Object represents a data point of some type.
    To have a standardized interpretation of the data there are a number of Data Point types (DPT).
    The DPT's is written like: xx.yyy, for example 14.056 for a 4-octet float, with Power info in Watts.
    The Major number (xx) describes the data type (format and encoding) - while the the minor (YYY) number
    describes the measurement with value range and unit.

    More DTP's are added as new needs come up, but this a list of some of the commonly used ones:
    1.yyy  boolean, like switching, on/off, open/close, move up/down, step
    2.yyy  2 x boolean, e.g. switching + priority control
    3.yyy  boolean + 3-bit unsigned value, e.g. dimming up/down
    4.yyy  character (8-bit)
    5.yyy  8-bit unsigned value, like dim value (0..100%), blinds position (0..100%)
    6.yyy  8-bit signed (2's complement), e.g. +/- %
    7.yyy  2-byte unsigned value, i.e. pulse counter
    8.yyy  2-byte signed (2's complement), e.g. +/- %
    9.yyy  2-byte float, e.g. temperature
    10.yyy time (3 bytes)
    11.yyy date (3 bytes)
    12.yyy 4-byte unsigned value, i.e. pulse counter
    13.yyy 4-byte signed (2's complement), i.e. flow, energy
    14.yyy 4-byte float, IEEE 754, i.e. Electrical measurements: current, power
    15.yyy access control
    16.yyy string -> 14 characters (14 x 8-bit)
    17.yyy scene number
    18.yyy scene control
    19.yyy date / time
    20.yyy 8-bit enumeration, e.g. HVAC mode ('auto', 'comfort', 'standby', 'economy', 'protection')
    28.yyy UTF-8
    29.yyy V64, 64-bit signed value
    232.yyy RGB [0,0,0]...[255,255,255]

    """

    payload_type: type[DPTArray | DPTBinary]
    payload_length: int = cast(int, None)  # only used for DPTArray
    dpt_main_number: int | None = None
    dpt_sub_number: int | None = None
    value_type: str | None = None
    unit: str | None = None
    ha_device_class: str | None = None

    @classmethod
    @abstractmethod
    def from_knx(cls, payload: DPTArray | DPTBinary) -> Any:
        """
        Parse/deserialize from KNX/IP payload data.

        Raise `CouldNotParseTelegram` for wrong payload
        or `ConversionError` for unparsable value.
        """
        # raw = cls.validate_payload(payload)

    @classmethod
    def validate_payload(cls, payload: DPTArray | DPTBinary) -> tuple[int, ...]:
        """
        Test if payload has the correct length and type for given DPT.

        Return tuple of raw values.
        Raise CouldNotParseTelegram if payload type or length is invalid for DPT.
        """
        if cls.payload_type is DPTArray and isinstance(payload, DPTArray):
            if cls.payload_length == len(payload.value):
                return payload.value

            raise CouldNotParseTelegram(
                f"Invalid payload length for {cls.__name__}",
                payload=payload,
                expected_length=cls.payload_length,
            )

        if cls.payload_type is DPTBinary and isinstance(payload, DPTBinary):
            # wrap in tuple for consistent return signature
            return (payload.value,)

        raise CouldNotParseTelegram(
            f"Invalid payload type for {cls.__name__}",
            payload=payload,
            expected_type=cls.payload_type.__name__,
        )

    @classmethod
    @abstractmethod
    def to_knx(cls, value: Any) -> DPTArray | DPTBinary:
        """
        Serialize to KNX/IP raw data.

        Raise `ConversionError` for unparsable value.
        """

    @classmethod
    def __recursive_subclasses__(cls: T) -> Iterator[T]:
        """Yield all subclasses and their subclasses."""
        for subclass in cls.__subclasses__():
            yield from subclass.__recursive_subclasses__()
            if not isabstract(subclass):
                yield subclass

    @classmethod
    def dpt_class_tree(cls: T) -> Iterator[T]:
        """Yield class, all subclasses and their subclasses that are not abstract."""
        if not isabstract(cls):
            yield cls
        yield from cls.__recursive_subclasses__()

    @classmethod
    def has_distinct_dpt_numbers(cls) -> bool:
        """Return True if dpt numbers are defined (not inherited)."""
        return "dpt_main_number" in cls.__dict__ and "dpt_sub_number" in cls.__dict__

    @classmethod
    def has_distinct_value_type(cls) -> bool:
        """Return True if value_type is defined (not inherited)."""
        return "value_type" in cls.__dict__

    @classmethod
    def transcoder_by_dpt(
        cls: T, dpt_main: int, dpt_sub: int | None = None
    ) -> T | None:
        """Return Class reference of DPTBase subclass with matching DPT number."""
        for dpt in cls.dpt_class_tree():
            if dpt.has_distinct_dpt_numbers():
                if dpt_main == dpt.dpt_main_number and dpt_sub == dpt.dpt_sub_number:
                    return dpt
        return None

    @classmethod
    def transcoder_by_value_type(cls: T, value_type: str) -> T | None:
        """Return Class reference of DPTBase subclass with matching value_type."""
        for dpt in cls.dpt_class_tree():
            if dpt.has_distinct_value_type():
                if value_type == dpt.value_type:
                    return dpt
        return None

    @classmethod
    def parse_transcoder(cls: T, value_type: int | str | _DPTMainSubDict) -> T | None:
        """
        Return Class reference of DPTBase subclass from value_type or DPT number.

        `value_type` accepts
        - Integer: DPT main number
        - String: value_type or "." separated dpt main and sub numbers (eg. "9.001")
        - Mapping: "main" and "sub" keys with DPT main and sub numbers (in accordance to xknxproject data)
        """
        if isinstance(value_type, int):
            return cls.transcoder_by_dpt(value_type)
        if isinstance(value_type, str):
            string_type = value_type.strip()
            transcoder = cls.transcoder_by_value_type(string_type)
            if transcoder is None:
                # Try to parse the value_type if it is a string but not found by cls.transcoder_by_value_type()
                # for backwards compatibility (eg. "DPT-5") and strings representing numbers (eg. "7", "9.001")
                string_type = string_type.upper().strip(" DPT-")
                if string_type.isdigit():
                    transcoder = cls.transcoder_by_dpt(int(string_type))
                else:
                    try:
                        main, sub = map(int, string_type.split("."))
                        transcoder = cls.transcoder_by_dpt(dpt_main=main, dpt_sub=sub)
                    except (ValueError, IndexError):
                        pass
            return transcoder
        if isinstance(value_type, Mapping):
            try:
                main = int(value_type["main"])
                if (_sub := value_type.get("sub")) is not None:
                    _sub = int(_sub)
                else:
                    _sub = None
            except (KeyError, TypeError, ValueError):
                return None
            return cls.transcoder_by_dpt(dpt_main=main, dpt_sub=_sub)


class DPTNumeric(DPTBase):
    """Base class for KNX data point types decoding numeric values."""

    payload_type = DPTArray
    value_min: int | float
    value_max: int | float
    resolution: int | float

    @classmethod
    @abstractmethod
    def from_knx(cls, payload: DPTArray | DPTBinary) -> int | float:
        """Parse/deserialize from KNX/IP payload data."""

    @classmethod
    @abstractmethod
    def to_knx(cls, value: int | float) -> DPTArray:
        """Serialize to KNX/IP raw data."""


@dataclass(slots=True)
class DPTComplexData(ABC):
    """Base class for KNX data point types decoding complex values."""

    @classmethod
    @abstractmethod
    def from_dict(
        cls, data: Mapping[str, Any]
    ) -> DPTComplexData:  # py3.11: use typing.Self
        """Init from a dictionary."""

    @abstractmethod
    def as_dict(self) -> dict[str, Any]:
        """Create a JSON serializable dictionary."""


class DPTComplex(DPTBase, Generic[TComplexData]):
    """Base class for KNX data point types decoding complex values."""

    data_type: type[TComplexData]

    @classmethod
    @abstractmethod
    def from_knx(cls, payload: DPTArray | DPTBinary) -> TComplexData:
        """Parse/deserialize from KNX/IP payload data."""

    @classmethod
    def to_knx(cls, value: TComplexData | Mapping[str, Any]) -> DPTArray:
        """Serialize to KNX/IP raw data."""
        try:
            if isinstance(value, cls.data_type):
                return cls._to_knx(value)
            return cls._to_knx(cls.data_type.from_dict(value))
        except (ValueError, TypeError, AttributeError, ConversionError) as err:
            raise ConversionError(
                f"Could not serialize {cls.__name__}: {err}", value=value
            ) from err

    @classmethod
    @abstractmethod
    def _to_knx(cls, value: TComplexData) -> DPTArray:
        """Serialize to KNX/IP raw data."""
