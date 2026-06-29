output_file="results.txt"
total=0
off=0
on=0

> "$output_file"

for f in data/*.fitacf.bz2 data/*.fitacf; do
    [ -f "$f" ] || continue

    base=$(basename "$f" .fitacf.bz2)
    base=$(basename "$base" .fitacf)

    result=$(./tx_detector "$f")

    if [ "$result" -eq 1 ]; then
        status="on"
        on=$((on + 1))
    else
        status="off"
        off=$((off + 1))
    fi

    echo "$base: $status" | tee -a "$output_file"
    total=$((total + 1))
done

summary="Summary: $total files, $off off, $on on"
echo "$summary" | tee -a "$output_file"