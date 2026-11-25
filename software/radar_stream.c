#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

enum { MAP_SIZE = 65536, MAGIC = 0x41524452, ABI = 0x00010000,
       MODE = 0x08 / 4, SEQUENCE = 0x0c / 4, FRAMES = 0x10 / 4,
       DROPPED = 0x14 / 4, LEVELS = 0x20 / 4, SCORES = 0x1000 / 4,
       CHANNELS = 6, PAIRS = 15, BINS = 65, COUNT = PAIRS * BINS };

struct snapshot {
    uint32_t seq, frames, dropped, energy[CHANNELS];
    int32_t score[COUNT];
};

static volatile sig_atomic_t stop;
static volatile uint32_t *io;

static void stop_capture(int signum)
{
    (void)signum;
    stop = 1;
}

static double monotonic_time(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return now.tv_sec + now.tv_nsec / 1e9;
}

static int open_radar(void)
{
    glob_t names;
    int fd = -1;
    if (glob("/sys/class/uio/uio*/name", 0, NULL, &names) != 0)
        return -1;

    for (size_t i = 0; i < names.gl_pathc; i++) {
        FILE *file = fopen(names.gl_pathv[i], "r");
        if (!file)
            continue;
        char name[128];
        int valid = fgets(name, sizeof(name), file) != NULL;
        fclose(file);
        if (!valid || strncmp(name, "acoustic-radar", strlen("acoustic-radar")) != 0)
            continue;
        unsigned int index;
        if (sscanf(names.gl_pathv[i], "/sys/class/uio/uio%u/name", &index) != 1)
            continue;
        char device[40];
        snprintf(device, sizeof(device), "/dev/uio%u", index);
        fd = open(device, O_RDWR | O_SYNC);
        break;
    }
    globfree(&names);
    return fd;
}

static int read_snapshot(struct snapshot *snapshot, uint32_t previous)
{
    snapshot->seq = io[SEQUENCE];
    if (!snapshot->seq || snapshot->seq == previous)
        return 0;
    snapshot->frames = io[0x38 / 4] == 0x50434d36 ? io[0x3c / 4] : io[FRAMES];
    snapshot->dropped = io[DROPPED];
    for (int i = 0; i < CHANNELS; i++)
        snapshot->energy[i] = io[LEVELS + i];
    for (int i = 0; i < COUNT; i++)
        snapshot->score[i] = (int32_t)io[SCORES + i];
    return io[SEQUENCE] == snapshot->seq;
}

static uint32_t checksum(const char *data)
{
    uint32_t crc = UINT32_MAX;
    for (; *data; data++) {
        crc ^= (uint8_t)*data;
        for (int i = 0; i < 8; i++)
            crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320u : 0);
    }
    return ~crc;
}

static void emit(const struct snapshot *snapshot, char source)
{
    static const char base64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    uint8_t quantized[COUNT];
    int index = 0;
    for (int a = 0; a < CHANNELS; a++) {
        for (int b = a + 1; b < CHANNELS; b++) {
            double scale = sqrt((double)snapshot->energy[a] * snapshot->energy[b]);
            for (int bin = 0; bin < BINS; bin++) {
                double value = scale > 0 ? 127.0 * snapshot->score[index] / scale : 0;
                value = fmax(-127, fmin(127, value));
                quantized[index++] = (uint8_t)(int8_t)lround(value);
            }
        }
    }
    char data[1600];
    int n = snprintf(data, sizeof(data), "AR1 %c %u %u %u %u,%u,%u,%u,%u,%u ", source,
            snapshot->seq, snapshot->frames, snapshot->dropped, snapshot->energy[0], snapshot->energy[1],
            snapshot->energy[2], snapshot->energy[3], snapshot->energy[4], snapshot->energy[5]);
    // COUNT is divisible by three, so this payload needs no Base64 padding.
    for (int i = 0; i < COUNT; i += 3) {
        unsigned int bits = ((unsigned int)quantized[i] << 16) | ((unsigned int)quantized[i + 1] << 8) | quantized[i + 2];
        data[n++] = base64[(bits >> 18) & 63];
        data[n++] = base64[(bits >> 12) & 63];
        data[n++] = base64[(bits >> 6) & 63];
        data[n++] = base64[bits & 63];
    }
    data[n] = '\0';
    printf("%s %08x\n", data, checksum(data));
    fflush(stdout);
}

static int test(const struct snapshot *snapshot)
{
    static const int delays[] = {2, 1, 0, 4, 3, 2};
    int pair = 0;
    for (int a = 0; a < CHANNELS; a++) {
        for (int b = a + 1; b < CHANNELS; b++, pair++) {
            const int32_t *pattern = snapshot->score + pair * BINS;
            int best = 0;
            for (int bin = 1; bin < BINS; bin++)
                if (pattern[bin] > pattern[best])
                    best = bin;
            if (best - 32 != delays[b] - delays[a] || pattern[best] <= 0) {
                fprintf(stderr, "RADAR-ERROR self-test pair %d/%d found lag %d\n", a + 1, b + 1, best - 32);
                return 1;
            }
        }
    }
    if (snapshot->dropped) {
        fprintf(stderr, "RADAR-ERROR dropped %u frames\n", snapshot->dropped);
        return 1;
    }
    emit(snapshot, 'T');
    puts("RADAR-SELFTEST PASS 15 pairs");
    return 0;
}

// The little-endian ARM sends a 16-byte header followed by interleaved
// signed 24-bit M1..M6. Each header identifies the first hardware sample.
static int stream_pcm(int fd)
{
    enum { RING = 8192, BLOCK = 512, PCM_BASE = 0x10000 / 4 };
    if (io[0x38 / 4] != 0x50434d36 || io[MODE] != 1) {
        fprintf(stderr, "Start live radar with the six-channel recording FPGA profile first\n");
        return 1;
    }
    volatile uint32_t *memory = mmap(NULL, 0x40000, PROT_READ, MAP_SHARED, fd, 0);
    if (memory == MAP_FAILED) {
        perror("PCM UIO map");
        return 1;
    }
    uint32_t next = io[FRAMES];
    const struct timespec nap = {0, 2000000};
    struct pollfd control = {STDIN_FILENO, POLLIN, 0};
    double last_block = monotonic_time();
    while (io[MODE] == 1) {
        if (poll(&control, 1, 0) > 0)
            return 0;   // Stop command, EOF or disconnected session.
        uint32_t available = io[FRAMES] - next;
        if (available < BLOCK) {
            if (monotonic_time() - last_block > 2.0) break;
            nanosleep(&nap, NULL);
            continue;
        }
        if (available >= RING) break;
        uint8_t data[BLOCK * CHANNELS * 3];
        for (unsigned mic = 0; mic < CHANNELS; mic++) {
            volatile uint32_t *channel = memory + PCM_BASE + RING * mic;
            for (unsigned i = 0; i < BLOCK; i++) {
                uint32_t sample = channel[(next + i) & (RING - 1)];
                unsigned offset = (i * CHANNELS + mic) * 3;
                data[offset] = (uint8_t)sample;
                data[offset + 1] = (uint8_t)(sample >> 8);
                data[offset + 2] = (uint8_t)(sample >> 16);
            }
        }
        if (io[FRAMES] - next >= RING || io[MODE] != 1) break;
        uint32_t header[4] = {0x364d4350, next, BLOCK, 48000}; // "PCM6"
        if (fwrite(header, sizeof(header), 1, stdout) != 1 ||
            fwrite(data, sizeof(data), 1, stdout) != 1 || fflush(stdout))
            return 1;
        next += BLOCK;
        last_block = monotonic_time();
    }
    fprintf(stderr, "Microphone recording interrupted: FPGA stopped or audio ring overrun\n");
    return 1;
}

int main(int argc, char **argv)
{
    int ethernet = argc == 2 && !strcmp(argv[1], "--ethernet");
    int pcm = argc == 2 && !strcmp(argv[1], "--pcm");
    if (argc != 2 || (!pcm && !ethernet && strcmp(argv[1], "--check") && strcmp(argv[1], "--stream") && strcmp(argv[1], "--self-test"))) {
        fprintf(stderr, "Usage: radar-stream --check | --stream | --ethernet | --pcm | --self-test\n");
        return 2;
    }

    int fd = open_radar();
    if (fd < 0) {
        fprintf(stderr, "RADAR-ERROR boot the radar FPGA profile first\n");
        return 1;
    }
    io = mmap(NULL, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (io == MAP_FAILED || io[0] != MAGIC || io[1] != ABI) {
        fprintf(stderr, "RADAR-ERROR incompatible radar FPGA registers\n");
        close(fd);
        return 1;
    }
    if (pcm) return stream_pcm(fd);
    if (!strcmp(argv[1], "--check")) {
        printf("RADAR-READY abi=%08x mode=%u seq=%u frames=%u dropped=%u\n",
               io[1], io[MODE], io[SEQUENCE], io[FRAMES], io[DROPPED]);
        return 0;
    }

    int self_test = !strcmp(argv[1], "--self-test");
    if (flock(fd, LOCK_EX | LOCK_NB) < 0 || (ethernet && io[MODE] == 3)) {
        fprintf(stderr, "RADAR-ERROR radar capture is busy\n");
        return 1;
    }
    signal(SIGINT, stop_capture);
    signal(SIGTERM, stop_capture);
    signal(SIGPIPE, SIG_IGN);
    // An older UART bridge may already be capturing without a file lock.
    // Observe its live frames until it releases the hardware.
    int owns_capture = !(ethernet && io[MODE] == 1);
    if (owns_capture) {
        io[MODE] = 0;
        (void)io[MODE];
        io[MODE] = self_test ? 3 : 1;
    }
    struct snapshot snapshot;
    uint32_t previous = owns_capture ? 0 : io[SEQUENCE];
    double deadline = monotonic_time() + (self_test ? 4.0 : 8.0);
    double next_emit = 0;
    int status = self_test;
    while (!stop && monotonic_time() < deadline) {
        if (!owns_capture && io[MODE] == 0) {
            io[MODE] = 1;
            owns_capture = 1;
            previous = 0;
        }
        if (!self_test) {
            struct pollfd input = { STDIN_FILENO, POLLIN, 0 };
            if (poll(&input, 1, 0) > 0) {
                char heartbeat[64];
                ssize_t count = read(STDIN_FILENO, heartbeat, sizeof(heartbeat));
                if (count > 0)
                    deadline = monotonic_time() + 8.0;
                else if (ethernet && (count == 0 || errno != EINTR))
                    break;
            }
        }
        double now = monotonic_time();
        if (now >= next_emit && read_snapshot(&snapshot, previous)) {
            previous = snapshot.seq;
            if (self_test) {
                status = test(&snapshot);
                break;
            }
            emit(&snapshot, 'L');
            if (ferror(stdout)) break;
            next_emit = ethernet ? now : now + 0.2;
        }
        const struct timespec pause = { .tv_sec = 0, .tv_nsec = ethernet ? 2000000 : 10000000 };
        nanosleep(&pause, NULL);
    }
    if (owns_capture) io[MODE] = 0;
    if (self_test && !previous) fprintf(stderr, "RADAR-ERROR no FPGA frame published\n");
    if (!self_test) puts("RADAR-END");
    munmap((void *)io, MAP_SIZE);
    close(fd);
    return status;
}
