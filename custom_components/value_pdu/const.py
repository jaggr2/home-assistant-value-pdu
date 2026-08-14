"""Constants for the Value IP PDU integration."""

from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

DOMAIN = "value_pdu"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NOMINAL_VOLTAGE = "nominal_voltage"
CONF_VOLTAGE_SENSOR = "voltage_sensor"
CONF_OUTLET_NAMES = "outlet_names"
CONF_OUTLET_LOCKED = "outlet_locked"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_NOMINAL_VOLTAGE = 230.0

OUTLET_COUNT = 8
DEFAULT_OUTLET_NAMES = [f"Outlet {index + 1}" for index in range(OUTLET_COUNT)]

# status.xml fields
FIELD_CURRENT = "cur0"
FIELD_TEMPERATURE = "tempBan"
FIELD_HUMIDITY = "humBan"
FIELD_STATUS = "stat0"
FIELD_OUTLET_STATE = "outletStat{index}"

# control_outlet.htm operations
OP_ON = "0"
OP_OFF = "1"
OP_CYCLE = "2"

MANUFACTURER = "VALUE"
MODEL = "IP PDU (8-port switched + metered)"

MIN_UPDATE_INTERVAL_SECONDS = 10

# Battery/auxiliary metadata is not used; these descriptors drive entity creation.
SENSOR_DESCRIPTORS: tuple = (
    {
        "key": "current",
        "name": "Total current",
        "device_class": SensorDeviceClass.CURRENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:current-ac",
    },
    {
        "key": "power",
        "name": "Total power",
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:flash",
    },
    {
        "key": "energy",
        "name": "Total energy",
        "device_class": SensorDeviceClass.ENERGY,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:counter",
    },
    {
        "key": "voltage",
        "name": "Voltage used",
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": UnitOfElectricPotential.VOLT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:sine-wave",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    {
        "key": "temperature",
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:thermometer",
    },
    {
        "key": "humidity",
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:water-percent",
    },
)

SWITCH_DEVICE_CLASS = SwitchDeviceClass.OUTLET
CYCLE_BUTTON_DEVICE_CLASS = ButtonDeviceClass.RESTART
