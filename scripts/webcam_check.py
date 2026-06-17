"""
Webcam-Test: MediaPipe Hands, live Landmark-Anzeige.
Beenden mit 'q'.
"""
import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError("Webcam nicht gefunden (Index 0)")

with mp_hands.Hands(
    model_complexity=0,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5,
) as hands:
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks:
            for lm in result.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)

                # Handgelenk-Koordinaten für Debug
                wrist = lm.landmark[0]
                h, w, _ = frame.shape
                cx, cy = int(wrist.x * w), int(wrist.y * h)
                cv2.putText(frame, f"Wrist {cx},{cy}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("MediaPipe Hands – q zum Beenden", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()
