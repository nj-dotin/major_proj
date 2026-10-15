#ifndef LD2450_DRIVER_H
#define LD2450_DRIVER_H

#include <Arduino.h>

#define LD2450_FRAME_LEN 30
#define LD2450_MAX_TARGETS 3

struct LD2450TargetData {
    int16_t x_mm;
    int16_t y_mm;
    int16_t speed_cms;
    uint16_t resolution_mm;
    bool is_valid;
};

struct LD2450Frame {
    uint8_t target_count;
    LD2450TargetData targets[LD2450_MAX_TARGETS];
};

class LD2450Driver {
private:
    uint8_t rx_buffer[LD2450_FRAME_LEN];
    uint8_t rx_index = 0;
    uint32_t parse_errors = 0;

    int16_t decodeSignMagnitude(uint16_t raw) {
        if (raw & 0x8000) {
            return -(int16_t)(raw & 0x7FFF);
        }
        return (int16_t)(raw & 0x7FFF);
    }

public:
    LD2450Driver() : rx_index(0), parse_errors(0) {}

    bool readByte(uint8_t b, LD2450Frame* out_frame) {
        rx_buffer[rx_index++] = b;

        // Check header as bytes arrive
        if (rx_index == 1 && rx_buffer[0] != 0xAA) { rx_index = 0; return false; }
        if (rx_index == 2 && rx_buffer[1] != 0xFF) { rx_index = 0; return false; }
        if (rx_index == 3 && rx_buffer[2] != 0x03) { rx_index = 0; return false; }
        if (rx_index == 4 && rx_buffer[3] != 0x00) { rx_index = 0; return false; }

        if (rx_index == LD2450_FRAME_LEN) {
            rx_index = 0;
            // Verify tail: 0x55 0xCC
            if (rx_buffer[28] == 0x55 && rx_buffer[29] == 0xCC) {
                out_frame->target_count = 0;
                for (int i = 0; i < LD2450_MAX_TARGETS; i++) {
                    int offset = 4 + (i * 8);
                    uint16_t raw_x = rx_buffer[offset] | (rx_buffer[offset + 1] << 8);
                    uint16_t raw_y = rx_buffer[offset + 2] | (rx_buffer[offset + 3] << 8);
                    uint16_t raw_speed = rx_buffer[offset + 4] | (rx_buffer[offset + 5] << 8);
                    uint16_t raw_res = rx_buffer[offset + 6] | (rx_buffer[offset + 7] << 8);

                    int16_t x = decodeSignMagnitude(raw_x);
                    int16_t y = decodeSignMagnitude(raw_y);
                    int16_t speed = decodeSignMagnitude(raw_speed);

                    if (x != 0 || y != 0 || speed != 0 || raw_res != 0) {
                        out_frame->targets[i].x_mm = x;
                        out_frame->targets[i].y_mm = y;
                        out_frame->targets[i].speed_cms = speed;
                        out_frame->targets[i].resolution_mm = raw_res;
                        out_frame->targets[i].is_valid = true;
                        out_frame->target_count++;
                    } else {
                        out_frame->targets[i].is_valid = false;
                    }
                }
                return true;
            } else {
                parse_errors++;
                return false;
            }
        }
        return false;
    }

    uint32_t getErrors() const { return parse_errors; }
};

#endif // LD2450_DRIVER_H
