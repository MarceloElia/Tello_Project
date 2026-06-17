from djitellopy import Tello
import time

tello = Tello()
tello.connect()
print("Akku vor Start:", tello.get_battery(), "%")

tello.takeoff()        # steigt auf ca. 1 m und schwebt
time.sleep(5)          # 5 Sekunden ruhig schweben
tello.land()           # sauber landen

print("Test fertig. Akku danach:", tello.get_battery(), "%")
