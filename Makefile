CC = cc
CFLAGS = -Wall -O2 -D_GNU_SOURCE \
    -I RSTLite/include/base \
    -I RSTLite/include/general \
    -I RSTLite/include/superdarn \
    -I src

LDFLAGS = -L RSTLite/lib \
    -Wl,-Bstatic \
    -lfit.1 -lradar.1 -lfitacf.1 -lraw.1 -ldmap.1 -lrcnv.1 -lrtime.1 \
    -Wl,-Bdynamic \
    -lm -lz

TARGET = tx_detector
SRC = src/viewer.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC) $(LDFLAGS)

clean:
	rm -f $(TARGET)