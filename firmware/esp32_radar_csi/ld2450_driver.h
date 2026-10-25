#ifndef LD2450_DRIVER_H
#define LD2450_DRIVER_H

#include <Arduino.h>
#include <string.h>

#define LD2450_FRAME_LEN 30
#define LD2450_MAX_TARGETS 3
#define LD2450_PARTIAL_TIMEOUT_MS 50

struct LD2450TargetData {
    int16_t x_mm = 0;
    int16_t y_mm = 0;
    int16_t speed_cms = 0;
    uint16_t resolution_mm = 0;
    bool is_valid = false;
};

struct LD2450Frame {
    uint8_t target_count = 0;
    LD2450TargetData targets[LD2450_MAX_TARGETS] = {};

    void clear() {
        target_count = 0;
        for (int i = 0; i < LD2450_MAX_TARGETS; i++) {
            targets[i].x_mm = 0;
            targets[i].y_mm = 0;
            targets[i].speed_cms = 0;
            targets[i].resolution_mm = 0;
            targets[i].is_valid = false;
        }
    }
};

class LD2450Driver {
private:
    uint8_t rx_buffer[LD2450_FRAME_LEN];
    uint8_t rx_index = 0;

    // Diagnostic counters and timing
    uint32_t total_bytes = 0;
    uint32_t valid_frames = 0;
    uint32_t invalid_tails = 0;
    uint32_t header_resyncs = 0;
    uint32_t last_byte_time_ms = 0;
    uint32_t last_frame_time_ms = 0;

    /**
     * Decode LD2450 sign-magnitude 16-bit integer.
     * HLK-LD2450 hardware standard (verified with actual physical sensor captures):
     * Bit 15 is sign bit (1 = positive, 0 = negative), bits 0-14 are magnitude.
     */
    int16_t decodeSignMagnitude(uint16_t raw) {
        if (raw & 0x8000) {
            return (int16_t)(raw & 0x7FFF);
        }
        return -(int16_t)(raw & 0x7FFF);
    }

    /**
     * Resynchronize the stream when header matching or tail verification fails.
     * Scans forward through rx_buffer for the earliest candidate 0xAA byte that
     * matches the AA FF 03 00 prefix for all available bytes in the window.
     * Does not shift or accept false candidates.
     */
    void resync() {
        header_resyncs++;
        for (uint8_t i = 1; i < rx_index; i++) {
            if (rx_buffer[i] == 0xAA) {
                uint8_t remaining = rx_index - i;
                bool match = true;
                if (remaining > 1 && rx_buffer[i + 1] != 0xFF) match = false;
                if (remaining > 2 && rx_buffer[i + 2] != 0x03) match = false;
                if (remaining > 3 && rx_buffer[i + 3] != 0x00) match = false;

                if (match) {
                    memmove(rx_buffer, &rx_buffer[i], remaining);
                    rx_index = remaining;
                    return;
                }
            }
        }
        rx_index = 0;
    }

public:
    LD2450Driver() : rx_index(0), total_bytes(0), valid_frames(0), invalid_tails(0), header_resyncs(0), last_byte_time_ms(0), last_frame_time_ms(0) {
        memset(rx_buffer, 0, sizeof(rx_buffer));
    }

    void resetRxBuffer() {
        rx_index = 0;
        memset(rx_buffer, 0, sizeof(rx_buffer));
    }

    /**
     * Ingests a single UART byte with stale frame timeout,
     * header validation, resynchronization, and tail validation.
     * 
     * @param b Incoming UART byte.
     * @param out_frame Pointer to frame structure to populate upon valid frame completion.
     * @return true if a complete, validated 30-byte frame was parsed; false otherwise.
     */
    bool readByte(uint8_t b, LD2450Frame* out_frame) {
        total_bytes++;
        uint32_t now = millis();

        // Check for partial frame timeout: if bytes stalled > 50ms, discard stale fragment
        if (rx_index > 0 && (now - last_byte_time_ms > LD2450_PARTIAL_TIMEOUT_MS)) {
            rx_index = 0;
            header_resyncs++;
        }
        last_byte_time_ms = now;

        // Bounds safety check
        if (rx_index >= LD2450_FRAME_LEN) {
            rx_index = 0;
        }

        // Store byte safely
        rx_buffer[rx_index++] = b;

        // Incremental header validation: AA FF 03 00
        if (rx_index == 1) {
            if (rx_buffer[0] != 0xAA) {
                rx_index = 0;
                return false;
            }
        } else if (rx_index == 2) {
            if (rx_buffer[1] != 0xFF) {
                resync();
                return false;
            }
        } else if (rx_index == 3) {
            if (rx_buffer[2] != 0x03) {
                resync();
                return false;
            }
        } else if (rx_index == 4) {
            if (rx_buffer[3] != 0x00) {
                resync();
                return false;
            }
        }

        // Complete 30-byte frame gathered: check tail and decode
        if (rx_index == LD2450_FRAME_LEN) {
            // Verify tail: 0x55 0xCC
            if (rx_buffer[28] == 0x55 && rx_buffer[29] == 0xCC) {
                valid_frames++;
                last_frame_time_ms = now;
                if (out_frame != nullptr) {
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
                            out_frame->targets[i].x_mm = 0;
                            out_frame->targets[i].y_mm = 0;
                            out_frame->targets[i].speed_cms = 0;
                            out_frame->targets[i].resolution_mm = 0;
                            out_frame->targets[i].is_valid = false;
                        }
                    }
                }
                rx_index = 0;
                return true;
            } else {
                invalid_tails++;
                resync();
                return false;
            }
        }
        return false;
    }

    // Diagnostic Counter and Timing Getters
    uint32_t getTotalBytes() const { return total_bytes; }
    uint32_t getValidFrames() const { return valid_frames; }
    uint32_t getInvalidTails() const { return invalid_tails; }
    uint32_t getHeaderResyncs() const { return header_resyncs; }
    uint32_t getErrors() const { return invalid_tails + header_resyncs; }
    uint32_t getLastByteTime() const { return last_byte_time_ms; }
    uint32_t getLastFrameTime() const { return last_frame_time_ms; }
    uint8_t  getBufferIndex() const { return rx_index; }
};

#endif // LD2450_DRIVER_H
