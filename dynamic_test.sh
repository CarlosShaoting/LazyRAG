cd /home/cuishaoting/testRag/LazyMind && \
KB='ds_dc26eb13c402b9a833e49a0983aaa23d' && \
PDF='/var/lib/lazymind/uploads/tenants/root/datasets/ds_dc26eb13c402b9a833e49a0983aaa23d/docs/files/upload_manual_dynamic/test_dynamic.pdf' && \
PADDLE_KEY='Your key' && \
MINERU_KEY='Your key' && \
MINERU_LOCAL='http://172.24.176.1:20234/api/v1/pdf_parse' && \
RESULTS=/tmp/e2e_dynamic_ocr_results.txt && : > "$RESULTS" && \

submit() {
  local label="$1"
  local ocr_json="$2"
  local task_id doc_id status
  task_id=$(uuidgen)
  doc_id="doc_${label}_$(date +%s)"
  echo "=== [$label] task_id=$task_id ==="
  docker exec lazymind-lazyllm-parse-worker-1 python3 -c "
import json, urllib.request, time
task_id='$task_id'
payload={
  'task_id': task_id,
  'kb_id': '$KB',
  'file_infos':[{'file_path':'$PDF','doc_id':'$doc_id','metadata':{'kb_id':'$KB'}}],
  'ocr_config': json.loads('''$ocr_json''')
}
req=urllib.request.Request('http://lazyllm-parse-server:8000/doc/add', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
print(urllib.request.urlopen(req, timeout=30).read().decode())
time.sleep(30)
" 2>&1
  for i in $(seq 1 60); do
    status=$(docker logs lazymind-lazyllm-parse-worker-1 2>&1 | grep "$task_id" | grep -E "Task completed successfully|Task completed with status TaskStatus.FAILED|Execute add task failed" | tail -1)
    if [ -n "$status" ]; then
      break
    fi
    [ $((i % 6)) -eq 0 ] && echo "poll $i..."
    sleep 5
  done
  echo "result: $status"
  if echo "$status" | grep -q "Task completed successfully"; then
    echo "$label: PASS" >> "$RESULTS"
  else
    echo "$label: FAIL | $status" >> "$RESULTS"
    docker logs lazymind-lazyllm-parse-worker-1 2>&1 | grep "$task_id" | grep -iE "mineru\.net|aistudio|paddleocr|401|403|Unauthorized|Connection refused|ERROR" | tail -6
  fi
  echo
}

submit 'none' '{"ocr_type":"none","ocr_url":""}'
submit 'paddle_key_only' '{"ocr_type":"paddleocr","paddle_api_key":"'"$PADDLE_KEY"'"}'
submit 'mineru_key_only' '{"ocr_type":"mineru","mineru_api_key":"'"$MINERU_KEY"'"}'
submit 'paddle_alias' '{"ocr_type":"paddle","paddle_api_key":"'"$PADDLE_KEY"'"}'
submit 'mineru_local' '{"ocr_type":"mineru","ocr_url":"'"$MINERU_LOCAL"'","mineru_api_key":"'"$MINERU_KEY"'"}'

echo '======== SUMMARY ========'
cat "$RESULTS"