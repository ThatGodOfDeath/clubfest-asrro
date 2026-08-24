#include <SoftwareSerial.h>

#define RX_PIN 8
#define LED_PIN 13

SoftwareSerial rfidSerial(RX_PIN, -1);

void setup() {
  Serial.begin(9600);
  rfidSerial.begin(9600);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println("RFID_TERMINAL_READY");
}

void loop() {
  static bool reading = false;
  static char rfidBuffer[14];
  static int index = 0;

  while (rfidSerial.available()) {

    char c = rfidSerial.read();

    // Start of RFID frame
    if ((unsigned char)c == 0x02) {
      reading = true;
      index = 0;
      rfidBuffer[index++] = c;
    }

    else if (reading) {

      if (index < 14) {
        rfidBuffer[index++] = c;
      }

      // Complete frame
      if (index >= 14) {

        reading = false;

        // Verify stop byte
        if ((unsigned char)rfidBuffer[13] == 0x03) {

          /*
           * RDM6300 frame:
           *
           * Byte 0  = 0x02
           * Bytes 1-10 = RFID data
           * Bytes 11-12 = checksum
           * Byte 13 = 0x03
           *
           * We send the 10 data characters to Python.
           */

          Serial.print("RFID:");

          for (int i = 1; i <= 10; i++) {
            Serial.print(rfidBuffer[i]);
          }

          Serial.println();

          // LED feedback
          digitalWrite(LED_PIN, HIGH);
          delay(200);
          digitalWrite(LED_PIN, LOW);
        }
      }
    }
  }
}