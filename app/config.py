"""配置管理模块"""
import configparser
import os

class Config:
    """配置管理类"""
    
    def __init__(self, config_file='config.ini'):
        """初始化配置"""
        self.config = configparser.ConfigParser()
        
        # 尝试读取配置文件
        if os.path.exists(config_file):
            self.config.read(config_file, encoding='utf-8')
        
    def get_exchange_type(self):
        """获取交易所类型"""
        return self.config.get('exchange', 'type', fallback='okx')
    
    def get_server_port(self):
        """获取服务端口"""
        return self.config.getint('server', 'port', fallback=9100)
    
    def get_server_host(self):
        """获取服务地址"""
        return self.config.get('server', 'host', fallback='0.0.0.0')
    
    def is_cache_enabled(self):
        """是否启用缓存"""
        return self.config.getboolean('cache', 'enabled', fallback=True)
    
    def get_cache_ttl(self, interval):
        """获取指定interval的缓存TTL"""
        interval_normalized = interval.replace('min', 'm')
        key = f'ttl_{interval_normalized}'
        return self.config.getint('cache', key, fallback=600)
    
    def get_max_retries(self):
        """获取最大重试次数"""
        return self.config.getint('retry', 'max_retries', fallback=3)


# 全局配置实例
config = Config()

