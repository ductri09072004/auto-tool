FROM argoproj/argocd:latest

# Expose port
EXPOSE 8080

# Set environment variables for ArgoCD
ENV ARGOCD_SERVER_INSECURE=true
ENV ARGOCD_SERVER_ROOT_PATH=/
ENV ARGOCD_SERVER_OPERATION_PROCESSORS=10
ENV ARGOCD_SERVER_STATUS_PROCESSORS=20

# Install kubectl (needed for ArgoCD)
RUN apt-get update && apt-get install -y kubectl && rm -rf /var/lib/apt/lists/*

# Start ArgoCD server
CMD ["argocd-server", "--insecure"]
