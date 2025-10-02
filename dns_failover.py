import requests
import socket
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime


class CloudflareAPI:
    """Класс для работы с Cloudflare API"""
    
    def __init__(self, api_token: str, zone_id: str):
        self.api_token = api_token
        self.zone_id = zone_id
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.logger = logging.getLogger(__name__)
    
    def get_dns_record(self, domain_name: str, record_type: str = "A") -> Optional[Dict[str, Any]]:
        """Получить информацию о DNS записи"""
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records"
            params = {
                "name": domain_name,
                "type": record_type
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data["success"] and len(data["result"]) > 0:
                return data["result"][0]
            else:
                self.logger.warning(f"DNS запись для {domain_name} не найдена")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка при получении DNS записи: {e}")
            return None
    
    def update_dns_record(self, record_id: str, domain_name: str, ip_address: str, 
                         record_type: str = "A", ttl: int = 300) -> bool:
        """Обновить DNS запись"""
        try:
            url = f"{self.base_url}/zones/{self.zone_id}/dns_records/{record_id}"
            data = {
                "type": record_type,
                "name": domain_name,
                "content": ip_address,
                "ttl": ttl
            }
            
            response = requests.put(url, headers=self.headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            if result["success"]:
                self.logger.info(f"DNS запись успешно обновлена: {domain_name} -> {ip_address}")
                return True
            else:
                self.logger.error(f"Ошибка при обновлении DNS записи: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении DNS записи: {e}")
            return False


class ServerMonitor:
    """Класс для мониторинга доступности серверов"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
    
    def check_tcp_connection(self, ip: str, port: int) -> bool:
        """Проверить TCP соединение"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception as e:
            self.logger.debug(f"TCP проверка не удалась для {ip}:{port} - {e}")
            return False
    
    def check_http_connection(self, ip: str, port: int, path: str = "/") -> bool:
        """Проверить HTTP соединение"""
        try:
            protocol = "https" if port == 443 else "http"
            url = f"{protocol}://{ip}:{port}{path}"
            
            response = requests.get(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code < 500  # Любой код ответа меньше 500 считается успешным
            
        except Exception as e:
            self.logger.debug(f"HTTP проверка не удалась для {ip}:{port} - {e}")
            return False
    
    def check_server(self, ip: str, port: int, method: str = "tcp", path: str = "/") -> bool:
        """Проверить доступность сервера"""
        if method.lower() == "http":
            return self.check_http_connection(ip, port, path)
        else:
            return self.check_tcp_connection(ip, port)


class DNSFailover:
    """Основной класс для управления DNS failover"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Инициализация компонентов
        self.cloudflare = CloudflareAPI(
            config["cloudflare"]["api_token"],
            config["cloudflare"]["zone_id"]
        )
        
        self.monitor = ServerMonitor(config["monitoring"]["timeout"])
        
        # Счетчики неудачных проверок
        self.failure_counts = {}
        for server_name in config["servers"]:
            self.failure_counts[server_name] = 0
        
        # Текущий активный сервер
        self.current_active_server = None
        self._determine_current_active_server()
    
    def _determine_current_active_server(self):
        """Определить текущий активный сервер по DNS записи"""
        try:
            domain_name = self.config["cloudflare"]["domain_name"]
            record_type = self.config["dns"]["record_type"]
            
            dns_record = self.cloudflare.get_dns_record(domain_name, record_type)
            if dns_record:
                current_ip = dns_record["content"]
                
                # Найти сервер с этим IP
                for server_name, server_config in self.config["servers"].items():
                    if server_config["ip"] == current_ip:
                        self.current_active_server = server_name
                        self.logger.info(f"Текущий активный сервер: {server_name} ({current_ip})")
                        return
                
                self.logger.warning(f"Текущий IP {current_ip} не найден в конфигурации серверов")
            
        except Exception as e:
            self.logger.error(f"Ошибка при определении активного сервера: {e}")
        
        # Если не удалось определить, используем сервер с наивысшим приоритетом
        if not self.current_active_server:
            self.current_active_server = self._get_highest_priority_server()
            self.logger.info(f"Установлен сервер по умолчанию: {self.current_active_server}")
    
    def _get_highest_priority_server(self) -> str:
        """Получить сервер с наивысшим приоритетом (наименьшее значение priority)"""
        return min(self.config["servers"].items(), 
                  key=lambda x: x[1]["priority"])[0]
    
    def _get_next_available_server(self) -> Optional[str]:
        """Получить следующий доступный сервер по приоритету"""
        # Сортируем серверы по приоритету
        sorted_servers = sorted(
            self.config["servers"].items(),
            key=lambda x: x[1]["priority"]
        )
        
        # Проверяем каждый сервер начиная с наивысшего приоритета
        for server_name, server_config in sorted_servers:
            if server_name == self.current_active_server:
                continue
            
            # Проверяем доступность сервера
            if self._check_server_health(server_name):
                return server_name
        
        return None
    
    def _check_server_health(self, server_name: str) -> bool:
        """Проверить здоровье сервера"""
        server_config = self.config["servers"][server_name]
        monitoring_config = self.config["monitoring"]
        
        is_healthy = self.monitor.check_server(
            server_config["ip"],
            server_config["port"],
            monitoring_config.get("check_method", "tcp"),
            monitoring_config.get("http_check_path", "/")
        )
        
        if is_healthy:
            self.failure_counts[server_name] = 0
            self.logger.debug(f"Сервер {server_name} ({server_config['ip']}) доступен")
        else:
            self.failure_counts[server_name] += 1
            self.logger.warning(
                f"Сервер {server_name} ({server_config['ip']}) недоступен "
                f"({self.failure_counts[server_name]} раз)"
            )
        
        return is_healthy
    
    def _switch_to_server(self, new_server: str) -> bool:
        """Переключиться на указанный сервер"""
        try:
            server_config = self.config["servers"][new_server]
            domain_name = self.config["cloudflare"]["domain_name"]
            record_type = self.config["dns"]["record_type"]
            ttl = self.config["dns"]["ttl"]
            
            # Получить текущую DNS запись
            dns_record = self.cloudflare.get_dns_record(domain_name, record_type)
            if not dns_record:
                self.logger.error("Не удалось получить текущую DNS запись")
                return False
            
            # Обновить DNS запись
            success = self.cloudflare.update_dns_record(
                dns_record["id"],
                domain_name,
                server_config["ip"],
                record_type,
                ttl
            )
            
            if success:
                old_server = self.current_active_server
                self.current_active_server = new_server
                self.failure_counts[new_server] = 0  # Сбросить счетчик неудач
                
                self.logger.info(
                    f"DNS переключен с {old_server} на {new_server} "
                    f"(IP: {server_config['ip']})"
                )
                return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при переключении на сервер {new_server}: {e}")
        
        return False
    
    def check_and_failover(self):
        """Выполнить проверку и переключение при необходимости"""
        try:
            failure_threshold = self.config["monitoring"]["failure_threshold"]
            
            # Проверить текущий активный сервер
            if not self.current_active_server:
                self.logger.error("Текущий активный сервер не определен")
                return
            
            is_current_healthy = self._check_server_health(self.current_active_server)
            
            # Если текущий сервер здоров, ничего не делаем
            if is_current_healthy:
                return
            
            # Если превышен порог неудач, пытаемся переключиться
            if self.failure_counts[self.current_active_server] >= failure_threshold:
                self.logger.warning(
                    f"Сервер {self.current_active_server} недоступен "
                    f"{self.failure_counts[self.current_active_server]} раз. "
                    f"Ищем альтернативный сервер..."
                )
                
                # Найти доступный альтернативный сервер
                next_server = self._get_next_available_server()
                
                if next_server:
                    self._switch_to_server(next_server)
                else:
                    self.logger.error("Нет доступных альтернативных серверов!")
            
        except Exception as e:
            self.logger.error(f"Ошибка в процессе проверки и переключения: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Получить текущий статус системы"""
        status = {
            "current_active_server": self.current_active_server,
            "timestamp": datetime.now().isoformat(),
            "servers": {}
        }
        
        for server_name, server_config in self.config["servers"].items():
            is_healthy = self._check_server_health(server_name)
            status["servers"][server_name] = {
                "ip": server_config["ip"],
                "port": server_config["port"],
                "priority": server_config["priority"],
                "healthy": is_healthy,
                "failure_count": self.failure_counts[server_name]
            }
        
        return status