#!/bin/bash

# Load the configuration from config.sh
source ./config.sh

# Function to clean up all processes upon exiting the script
cleanup() {
    echo "Cleaning up remote processes..."
    sshpass -p "$PASSWORD" ssh $USER@$SERVER1 "pkill -f 'python3 server_vllm.py --model meetkai/functionary-small-v2.5'"
    ssh $USER@$SERVER2 "pkill -f 'python3 coqui_api.py'"

    scp $USER@$SERVER1:$LLM_API_DIR/functionary.log ./
    scp $USER@$SERVER2:$TTS_API_DIR/coqui.log ./


    echo "Cleaning up local processes..."
    pkill -f 'python3 server.py'
    pkill -f 'yarn'

    echo "Cleanup completed."
    exit
}

# Trap SIGINT and SIGTERM to ensure cleanup is called when script exits
trap cleanup SIGINT SIGTERM




# Start remote processes
sshpass -p "$PASSWORD" ssh -f $USER@$SERVER1 "export PATH=$PYTHON_PATH:$PATH && cd $LLM_API_DIR; nohup python3 server_vllm.py --model 'meetkai/functionary-small-v2.5' --host 0.0.0.0 --port 5001 --max-model-len 8192 > functionary.log 2>&1 &"
sshpass -p "$PASSWORD" ssh -f $USER@$SERVER2 "export PATH=$PYTHON_PATH:$PATH && cd $TTS_API_DIR && rm -f coqui.log && nohup python3 coqui_api.py > coqui.log 2>&1 &"

rm -f server.log
rm -f web-client-ui/webui.log

# Starting local server
nohup python3 server.py > server.log 2>&1 &

# Starting WebUI in the specific directory
(cd web-client-ui && nohup yarn dev > webui.log 2>&1 &)

# Waiting for 5 seconds before outputting that all processes are running, to ensure that all processes have loaded up completely
sleep 5

echo "Coffeebot processes are now all running!"

# Keep script running to handle signals
wait
