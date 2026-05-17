from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)
for servo_num in range(4, 12):
    kit.servo[servo_num].set_pulse_width_range(600, 2400)

while True:
    servo_num = int(input("Enter a servo number (4-11): "))
    angle = float(input(f"Servo {servo_num}: Enter a servo angle (0-180): "))
    kit.servo[servo_num].angle = angle
