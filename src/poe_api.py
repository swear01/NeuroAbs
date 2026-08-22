from poe_api_wrapper import AsyncPoeApi, PoeApi
from check import *
import asyncio
import random
import time
import ssl
import traceback
import logging
from datetime import datetime
import os

def get_poe_tokens():
    p_b = os.environ.get("POE_P_B", "")
    p_lat = os.environ.get("POE_P_LAT", "")
    if not p_b or not p_lat:
        raise RuntimeError("POE_P_B and POE_P_LAT must be set.")
    return {"p-b": p_b, "p-lat": p_lat}

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    log_filename = f'logs/errors_{datetime.now().strftime("%Y%m%d")}.log'
    
    logging.basicConfig(
        # level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

async def send_message_with_retry(client, bot_name, message, max_retries=3):
    for attempt in range(max_retries):
        try:
            full_response = ""
            async for chunk in client.send_message(bot=bot_name, message=message):
                if isinstance(chunk, dict):
                    if "response" in chunk:
                        full_response += chunk["response"]
                    elif "text" in chunk:
                        full_response += chunk["text"]
            return full_response
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = random.uniform(5, 10) * (attempt + 1)
                print(f"Message send attempt {attempt + 1} failed: {str(e)}")
                print(f"Waiting {wait_time:.2f} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                raise

async def create_client_with_retry(tokens):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = AsyncPoeApi(tokens=tokens)
            await asyncio.sleep(random.uniform(2, 5))
            await client.create()  # Changed to await the create() call
            return client
            
        except RuntimeError as e:
            if "Rate limit exceeded" in str(e) or "Timed out" in str(e):
                if attempt < max_retries - 1:
                    wait_time = random.uniform(5, 10) * (attempt + 1)
                    print(f"Attempt {attempt + 1} failed, waiting {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            else:
                raise
        except Exception as e:
            print(f"Unexpected error during client creation: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = random.uniform(5, 10) * (attempt + 1)
                print(f"Waiting {wait_time:.2f} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                raise

async def main(bot_name, message):
    tokens = get_poe_tokens()

    client = None
    try:
        client = await create_client_with_retry(tokens)
        
        # 直接在main函数中处理消息
        full_response = ""
        try:
            async for chunk in client.send_message(bot=bot_name, message=message):
                if isinstance(chunk, dict):
                    if "response" in chunk:
                        full_response += chunk["response"]
                    elif "text" in chunk:
                        full_response += chunk["text"]
            return full_response
            
        except asyncio.TimeoutError:
            print("Request timed out")
            raise
        except Exception as e:
            print(f"Error while getting response: {str(e)}")
            raise

    finally:
        if client:
            try:
                if hasattr(client, '_session'):
                    await client._session.aclose()
                if hasattr(client, 'close'):
                    await client.close()
            except Exception as e:
                print(f"Error closing client session: {str(e)}")


def create_client(max_retries=2, backoff_factor=1):
    tokens = get_poe_tokens()
    for attempt in range(max_retries):
        try:
            client = PoeApi(tokens)
            return client
        except ssl.SSLError as e:
            logging.error(f"SSL Error in create_client: {str(e)}")
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff_factor * (2 ** attempt))
        except Exception as e:
            logging.error(f"Error in create_client - Attempt {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff_factor * (2 ** attempt))
    return None

def run_api(bot_name, message, original_statement, width_map):
    print(bot_name + '\n')
    print(message + '\n')
    setup_logging()
    
    max_attempts = 2
    attempt = 0
    client = None
    backoff_time = 1
    
    while attempt < max_attempts:
        try:
            client = create_client()
            if not client:
                raise Exception("Cannot construct the client")
                
            for chunk in client.send_message(bot=bot_name, message=message):
                response = chunk["text"]
        
            
                
            result = check_implies(original_statement, response, width_map)

            return response, result 

        except Exception as e:
            attempt += 1
            attempt += 1
            logging.error(f"\n{'='*50}\n"
                        f"错误发生时的上下文:\n"
                        f"Bot: {bot_name}\n"
                        f"Original Statement: {original_statement}\n"
                        f"response: {response if 'response' in locals() else 'Not set'}\n"
                        f"{'='*50}")
            logging.error(f"尝试 {attempt}/{max_attempts} 失败: {str(e)}")
            logging.error(f"错误详细信息:\n{traceback.format_exc()}")
            error_msg = f"尝试 {attempt}/{max_attempts} 失败: {str(e)}"
            logging.error(error_msg)
            logging.error(f"错误详细信息:\n{traceback.format_exc()}")
            
            if attempt >= max_attempts:
                final_error = f"达到最大重试次数，操作失败: {str(e)}"
                logging.error(final_error)
                return None, 'fail'
                
            time.sleep(backoff_time)
            backoff_time = min(backoff_time * 2, 30)
            
        finally:
            # 移除了 client.close() 的调用
            pass


# def run_api(bot_name, message, original_statement, width_map):
#     print(bot_name + '\n')
#     print(message + '\n')
#     tokens = get_poe_tokens()
#     loop = None
#     try:
#         # try:
#         #     loop = asyncio.get_event_loop()
#         # except RuntimeError:
#         #     loop = asyncio.new_event_loop()
#         #     asyncio.set_event_loop(loop)
        
#         # # 添加随机延迟
#         # loop.run_until_complete(asyncio.sleep(random.uniform(2, 5)))
        
#         # # 运行主要逻辑
#         # response = loop.run_until_complete(asyncio.wait_for(main(bot_name, message), timeout=60))
#         client = PoeApi(tokens)
#         for chunk in client.send_message(bot=bot_name, message=message):
#             response = chunk["text"]


#         # print(response)
#         check_implies(original_statement, response, width_map)
        
#     except Exception as e:
#         print(f"Error occurred: {str(e)}")
#         raise
        
#     # finally:
#     #     if loop and loop.is_running():
#     #         try:
#     #             # 取消所有待处理的任务
#     #             tasks = asyncio.all_tasks(loop)
#     #             for task in tasks:
#     #                 task.cancel()
                
#     #             # 等待所有任务完成
#     #             if tasks:
#     #                 loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                
#     #             # 清理并关闭循环
#     #             loop.run_until_complete(loop.shutdown_asyncgens())
#     #             loop.run_until_complete(asyncio.sleep(0))
#     #             loop.close()
#     #         except Exception as e:
#     #             print(f"Error during loop cleanup: {str(e)}")