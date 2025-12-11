"""
Custom middleware for handling Azure App Service internal requests
"""
from django.core.exceptions import DisallowedHost
from django.conf import settings
import os


class AzureInternalIPMiddleware:
    """
    Middleware to allow Azure internal IP addresses (169.254.x.x) for health probes
    and load balancer checks.
    
    This middleware runs before CommonMiddleware and adds Azure internal IPs to
    ALLOWED_HOSTS if they're not already present.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Check if we're on Azure
        self.is_azure = bool(os.environ.get("WEBSITE_HOSTNAME"))
    
    def __call__(self, request):
        # Only run on Azure
        if self.is_azure:
            # Check if the host is an Azure internal IP (169.254.x.x)
            host = request.get_host().split(':')[0]  # Remove port if present
            
            if host.startswith('169.254.'):
                # This is an Azure internal IP - add it to ALLOWED_HOSTS if not present
                # Convert to list if needed
                current_hosts = list(settings.ALLOWED_HOSTS) if isinstance(settings.ALLOWED_HOSTS, (list, tuple)) else []
                
                if host not in current_hosts and '*' not in current_hosts:
                    # Add the host to ALLOWED_HOSTS for this request
                    settings.ALLOWED_HOSTS = current_hosts + [host]
        
        try:
            response = self.get_response(request)
        except DisallowedHost as e:
            # If we still get DisallowedHost for an Azure IP, allow it
            host = request.get_host().split(':')[0]
            if self.is_azure and host.startswith('169.254.'):
                # Re-add to ALLOWED_HOSTS and retry
                current_hosts = list(settings.ALLOWED_HOSTS) if isinstance(settings.ALLOWED_HOSTS, (list, tuple)) else []
                settings.ALLOWED_HOSTS = current_hosts + [host]
                response = self.get_response(request)
            else:
                raise
        
        return response

