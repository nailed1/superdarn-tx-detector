for f in data/*.fitacf.bz2 data/*.fitacf; do
    [ -f "$f" ] || continue
    base=$(basename "$f" .fitacf.bz2)
    base=$(basename "$base" .fitacf)
    ./tx_detector "$f" > "csv/${base}.csv"
    echo "Done: $f"
done