from djitellopy import Tello

tello = Tello()
tello.connect()

print("Akku:", tello.get_battery(), "%")
print("Temperatur:", tello.get_temperature(), "°C")
print("Barometer:", tello.get_barometer())

