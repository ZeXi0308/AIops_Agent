import os
import re
import asyncio
import paramiko
import contextlib
import logging
import json
import time
import uuid
from pathlib import Path
from subprocess import call
from typing import Dict, Any, List
from mcp.server.fastmcp import FastMCP
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RRCMsgExtractor")
mcp = FastMCP(name="RRCMsgExtractor")
TARGET_DIR = os.getenv("RRC_TMP_DIR", "/tmp/rrc_extractor")
REMOTE_RESULT_DIR = os.getenv("REMOTE_RESULT_DIR", "/local/KunlunAgentGenFiles")
REMOTE_BASE_URL = os.getenv("REMOTE_BASE_URL", "https://iodt.gic.ericsson.se/KunlunAgentGenFiles")
LTNG_DECODER = os.getenv("LTNG_DECODER_PATH", "/proj/toolswarehouse_sero/linux/production/wh/dtd/RHE64-8.7/ltng/latest/bin/ltng-decoder")
SSH_HOST = os.getenv("RRC_SSH_HOST", "10.86.71.100")
SSH_PORT = int(os.getenv("RRC_SSH_PORT", "22"))
SSH_USERNAME = os.getenv("RRC_SSH_USER", "RMFTMXCFLZ")
SSH_PASSWORD = os.getenv("RRC_SSH_PASS", "s$TxE#tOO1+>~3a$/5RI")

ssh_pool = []

async def get_ssh_connection():
    try:
        if ssh_pool:
            return ssh_pool.pop()
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SSH_HOST, SSH_PORT, SSH_USERNAME, SSH_PASSWORD)
        logger.info("Created new SSH connection")
        return ssh
    except Exception as e:
        logger.error(f"SSH connection failed: {str(e)}")
        raise

async def release_ssh_connection(ssh):
    ssh_pool.append(ssh)

async def fetch_via_sftp(remote_path: str) -> Path:
    ssh = await get_ssh_connection()
    target_dir = Path(TARGET_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / Path(remote_path).name
    
    try:
        sftp = ssh.open_sftp()
        logger.info(f"Downloading remote file: {remote_path} to {local_path}")
        sftp.get(remote_path, str(local_path))
        return local_path
    except FileNotFoundError:
        logger.error(f"Remote file not found: {remote_path}")
        raise
    finally:
        sftp.close()
        await release_ssh_connection(ssh)

async def upload_via_sftp(local_path: Path, remote_dir: str) -> str:
    ssh = await get_ssh_connection()
    remote_path = f"{remote_dir.rstrip('/')}/{local_path.name}"
    
    try:
        sftp = ssh.open_sftp()
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            sftp.mkdir(remote_dir)
        
        sftp.put(str(local_path), remote_path)
        logger.info(f"Uploaded file to remote: {remote_path}")
        return remote_path
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise
    finally:
        sftp.close()
        await release_ssh_connection(ssh)

def decode_log(raw_filename: Path) -> Path:
    print("\n\nLog name is:" + str(raw_filename) + " Size: " + str(
        round(os.path.getsize(raw_filename) / (float(1024 * 1024)), 2)) + "MBytes" + "\nDecoding the log...")
    
    target_dir = Path(TARGET_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    decoded_filename = target_dir / (raw_filename.name + ".dec")
    
    call("cat " + str(raw_filename) + " | " + LTNG_DECODER + " -s " + " > " + str(decoded_filename), shell=True)
    return decoded_filename

def convert2hex(data):
    for i in range(0, len(data), 16):
        line = ' '.join(f"{b:02X}" for b in data[i:i+16])
        print(line)

def extract_msg_data_from_line(line):
    try:
        matches = re.findall(r'\[\d+\]\s*=\s*(\d+)', line)
        return [int(val) for val in matches] if matches else None
    except Exception as e:
        print(f"Error extracting msg_data: {e}")
        return None

def extract_timestamp(line):
    try:
        match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', line)
        return match.group(1) if match else None
    except Exception as e:
        print(f"Error extracting timestamp: {e}")
        return None

def extract_ue_trace_id(line):
    try:
        match = re.search(r'ue_trace_id\s*=\s*(0x[0-9A-Fa-f]+)', line)
        return match.group(1) if match else None
    except Exception as e:
        print(f"Error extracting ue_trace_id: {e}")
        return None

def update_results_tmp(results_tmp, ue_trace_id, new_crnti):
    new_crnti = str(new_crnti)
    if ue_trace_id not in results_tmp:
        print(f"[WARN] ue_trace_id '{ue_trace_id}' not found in results_tmp")
        return
    rrc_setup_list = results_tmp[ue_trace_id].get('rrcSetup', [])
    for item in rrc_setup_list:
        if item.get('C-RNTI') is None:
            item['C-RNTI'] = new_crnti
    rrc_reconfig_list = results_tmp[ue_trace_id].get('rrcReconfig', [])
    for item in rrc_reconfig_list:
        current = item.get('C-RNTI')
        if current is None:
            item['C-RNTI'] = new_crnti
        elif isinstance(current, str):
            existing_set = set([x.strip() for x in current.split('or')])
            if new_crnti not in existing_set:
                item['C-RNTI'] = current + ' or ' + new_crnti

def extract_rrc_messages(file_path: Path) -> Dict[str, Any]:
    results_tmp = {}
    crnti_ue_trace_id_tmp = {}
    
    logger.info(f"Extracting RRC messages from: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if 'asn_type = "DL-CCCH-Message"' in line:
                    timestamp = extract_timestamp(line)
                    msg_data = extract_msg_data_from_line(line)
                    ue_trace_id = extract_ue_trace_id(line)
                    if ue_trace_id not in results_tmp:
                        results_tmp[ue_trace_id] = {'rrcSetup': [], 'rrcReconfig': []}
                    if timestamp and msg_data:
                        msg_entry = {
                            "timestamp": timestamp,
                            "C-RNTI": None,
                            "msg_data": msg_data,
                            "msg_data_hex": []
                        }
                        for j in range(0, len(msg_data), 16):
                            hex_line = ' '.join(f"{b:02X}" for b in msg_data[j:j+16])
                            msg_entry["msg_data_hex"].append(hex_line)
                        
                        results_tmp[ue_trace_id]['rrcSetup'].append(msg_entry)

                if "message c1 : rrcReconfiguration :" in line:
                    for j in range(i, -1, -1):  
                        time_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', lines[j])
                        if time_match:
                            if 'rat_type = "NR"' in lines[j] and 'asn_type = "DL-DCCH-Message"' in lines[j]:
                                timestamp = extract_timestamp(lines[j])
                                msg_data = extract_msg_data_from_line(lines[j])
                                ue_trace_id = extract_ue_trace_id(lines[j])
                                if timestamp and msg_data:
                                    if ue_trace_id not in results_tmp:
                                        results_tmp[ue_trace_id] = {'rrcSetup': [], 'rrcReconfig': []}
                                    
                                    msg_entry = {
                                        "timestamp": timestamp,
                                        "C-RNTI": None,
                                        "msg_data": msg_data,
                                        "msg_data_hex": []
                                    }
                                    for k in range(0, len(msg_data), 16):
                                        hex_line = ' '.join(f"{b:02X}" for b in msg_data[k:k+16])
                                        msg_entry["msg_data_hex"].append(hex_line)
                                    
                                    results_tmp[ue_trace_id]['rrcReconfig'].append(msg_entry)
                            break

                if 'C-RNTI' in line:
                    crnti_match = re.search(r'C-RNTI\s*:\s*(\d+)', line)
                    if crnti_match:
                        crnti = int(crnti_match.group(1)) 
                        for k in range(i, -1, -1):  
                            time_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', lines[k])
                            if time_match:
                                ue_trace_id = extract_ue_trace_id(lines[k])
                                if crnti and ue_trace_id:
                                    key = (crnti, ue_trace_id)
                                    crnti_ue_trace_id_tmp[key] = {
                                        "C-RNTI": crnti,
                                        "ue_trace_id": ue_trace_id
                                    }
                                break  

        crnti_ue_trace_id_tmp = list(crnti_ue_trace_id_tmp.values())
        for item in crnti_ue_trace_id_tmp:
            ue_trace_id = item.get('ue_trace_id')
            c_rnti = item.get('C-RNTI')
            if ue_trace_id and c_rnti:
                update_results_tmp(results_tmp, ue_trace_id, c_rnti)

        logger.info(f"Extracted RRC messages for {len(results_tmp)} UEs")
        return results_tmp
        
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        raise
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        raise

def check_log_type(file_path: Path, decode_flag=False):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i in range(30):
                line = f.readline()
                if not line:
                    break  
                if "decoder_default_profile.json" in line:
                    return file_path, decode_flag
        decode_flag = True
        return decode_log(file_path), decode_flag
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        raise
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        print('Please provide a valid L3 log. Both raw and decoded formats are supported.')
        raise

class EnhancedJSONEncoder(json.JSONEncoder):
    def _fix_msg_data_format(self, json_str):
        import re
        
        def replace_msg_data(match):
            array_content = match.group(1)
            numbers = re.findall(r'\d+', array_content)
            if not numbers:
                return match.group(0)
            
            nums = [int(n) for n in numbers]
            lines = []
            base_indent = "      "
            
            for i in range(0, len(nums), 16):
                chunk = nums[i:i+16]
                line = ", ".join(str(x) for x in chunk)
                if i + 16 < len(nums):
                    line += ","
                lines.append(base_indent + line)
            
            formatted_array = "[\n" + "\n".join(lines) + "\n    ]"
            return f'"msg_data": {formatted_array}'
        
        pattern = r'"msg_data":\s*\[\s*([\d\s,\n]+?)\s*\]'
        result = re.sub(pattern, replace_msg_data, json_str, flags=re.DOTALL)
        return result
        
    def encode(self, o):
        result = super().encode(o)
        result = self._fix_msg_data_format(result)
        return result

def generate_txt_content(result_data: Dict[str, Any]) -> str:
    txt_content = []
    txt_content.append("RRC Message Extraction Results")
    txt_content.append("=" * 50)
    txt_content.append("")
    
    for ue_trace_id, ue_data in result_data.items():
        txt_content.append(f"UE Trace ID: {ue_trace_id}")
        txt_content.append("-" * 40)
        
        rrc_setup_msgs = ue_data.get('rrcSetup', [])
        if rrc_setup_msgs:
            txt_content.append(f"RRC Setup Messages:")
            for i, msg in enumerate(rrc_setup_msgs, 1):
                txt_content.append(f"  Message {i}:")
                txt_content.append(f"    Timestamp: {msg.get('timestamp', 'N/A')}")
                txt_content.append(f"    C-RNTI: {msg.get('C-RNTI', 'N/A')}")
                
                msg_data_hex = msg.get('msg_data_hex', [])
                if msg_data_hex:
                    txt_content.append(f"    Message Data (Hex):")
                    for hex_line in msg_data_hex:
                        txt_content.append(f"      {hex_line}")
                txt_content.append("")
        
        rrc_reconfig_msgs = ue_data.get('rrcReconfig', [])
        if rrc_reconfig_msgs:
            txt_content.append(f"RRC Reconfiguration Messages:")
            for i, msg in enumerate(rrc_reconfig_msgs, 1):
                txt_content.append(f"  Message {i}:")
                txt_content.append(f"    Timestamp: {msg.get('timestamp', 'N/A')}")
                txt_content.append(f"    C-RNTI: {msg.get('C-RNTI', 'N/A')}")
                
                msg_data_hex = msg.get('msg_data_hex', [])
                if msg_data_hex:
                    txt_content.append(f"    Message Data (Hex):")
                    for hex_line in msg_data_hex:
                        txt_content.append(f"      {hex_line}")
                txt_content.append("")
        
        txt_content.append("=" * 50)
        txt_content.append("")
    
    return "\n".join(txt_content)

@mcp.tool(
    name="extract_rrc_msgs", 
    description=("Obtain log files from the remote server, parse the logs (.raw or .dec) and extract the RRC Setup/Reconfig messages under the UE trace. The result will be saved to remote files (both JSON and TXT formats) and the url linked to the txt file will be returned."
    "The url linked to txt should be shown to the user. And your answer should not contain other words."
    
    )
)
async def extract_rrc_msgs(remote_log_path: str) -> Dict[str, Any]:
    temp_files = []
    local_result_json_path = None
    local_result_txt_path = None
    
    try:
        Path(TARGET_DIR).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Fetching remote log: {remote_log_path}")
        local_raw_path = await fetch_via_sftp(remote_log_path)
        temp_files.append(local_raw_path)
        
        logger.info("Checking log type and decoding if necessary")
        process_path, decode_flag = check_log_type(local_raw_path)
        if decode_flag and process_path != local_raw_path:
            temp_files.append(process_path)
        
        logger.info("Extracting RRC messages")
        result = extract_rrc_messages(process_path)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = Path(remote_log_path).name
        
        result_json_filename = f"{filename}_{timestamp}_{unique_id}.json"
        local_result_json_path = Path(TARGET_DIR) / result_json_filename
        
        with open(local_result_json_path, 'w', encoding='utf-8') as f:
            encoder = EnhancedJSONEncoder(indent=2, ensure_ascii=False)
            formatted_json = encoder.encode(result)
            f.write(formatted_json)
        
        result_txt_filename = f"{filename}_{timestamp}_{unique_id}.txt"
        local_result_txt_path = Path(TARGET_DIR) / result_txt_filename
        
        txt_content = generate_txt_content(result)
        with open(local_result_txt_path, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        
        remote_result_json_path = await upload_via_sftp(local_result_json_path, REMOTE_RESULT_DIR)
        logger.info(f"JSON result uploaded to remote: {remote_result_json_path}")
        
        remote_result_txt_path = await upload_via_sftp(local_result_txt_path, REMOTE_RESULT_DIR)
        logger.info(f"TXT result uploaded to remote: {remote_result_txt_path}")
        
        txt_name = Path(remote_result_txt_path).name
        base = REMOTE_BASE_URL.rstrip('/')
        txt_url = f"{base}/{txt_name}"
        
        success_msg = (
            f"RRC message parsing completed. Results saved to TXT file:\n"
            f"TXT URL:  {txt_url}\n"
            f"The user can open this URL in their browser to view the results.\n"
            "Please notice, when you return this result to the user, your response must be this format: TXT URL: {txt_url} . Do not say any other words."
        )
        return {"result": success_msg}
    
    except FileNotFoundError as e:
        error_msg = f"cannot find the remote log: {remote_log_path}"
        logger.error(error_msg)
        return {"error": error_msg}
    
    except paramiko.SSHException as e:
        error_msg = f"SSH connection failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    
    except Exception as e:
        error_msg = f"processing error: {str(e)}"
        logger.exception(f"processing error: {remote_log_path}")
        return {"error": error_msg}
    
    finally:
    
        for file_path in temp_files:
            try:
                if isinstance(file_path, Path) and file_path.exists():
                    file_path.unlink()
                    logger.info(f"clear the files: {file_path}")
            except Exception as e:
                logger.error(f"clearing {file_path} error: {str(e)}")
        
        if local_result_json_path and local_result_json_path.exists():
            try:
                local_result_json_path.unlink()
                logger.info(f"JSON files cleared: {local_result_json_path}")
            except Exception as e:
                logger.error(f"clearing JSON error: {str(e)}")
        
        if local_result_txt_path and local_result_txt_path.exists():
            try:
                local_result_txt_path.unlink()
                logger.info(f"TXT files cleared: {local_result_txt_path}")
            except Exception as e:
                logger.error(f"clearing TXT error: {str(e)}")

@contextlib.asynccontextmanager
async def lifespan(app):
    Path(TARGET_DIR).mkdir(parents=True, exist_ok=True)
    
    async with mcp.session_manager.run():
        logger.info("RRCMsgExtractor server starting")
        yield
    
    logger.info("terminating ssh connection")
    for ssh in ssh_pool:
        try:
            ssh.close()
        except:
            pass
    logger.info("server shut down")

app = Starlette(
    routes=[Mount("/", mcp.streamable_http_app())],
    lifespan=lifespan,
)

if __name__ == "__main__":
    port = int(os.getenv("RRC_TOOL_PORT", "8003"))
    
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=port,
        log_level="info"
    )