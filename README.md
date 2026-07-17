# DevPad: A Code Editor Powered by Amazon Web Services

DevPad is a real-time collaborative code editor and execution platform. It provides a seamless, low-latency environment for distributed teams to write, debug, and execute code concurrently directly from the browser. The application is built with a Python Flask backend, Flask-SocketIO for WebSocket communication, and a standard HTML/CSS/JS frontend.

## Key Features
- **Real-Time Collaboration**: State synchronization in real-time across multiple users using Socket.IO broadcast rooms.
- **Secure Code Execution**: Completely isolated and secure serverless code execution environment to run untrusted code without jeopardizing the main application server.
- **High Availability**: Built on a highly available, scalable, and resilient AWS architecture.

---

## AWS Infrastructure & Architecture

A primary focus of DevPad is its robust, highly available AWS deployment. The system employs a hybrid architecture, mixing IaaS for its stateful WebSocket server with FaaS for its stateless, insecure execution service.

### 1. Core Infrastructure & Networking
- **Amazon VPC**: The foundation is a custom Virtual Private Cloud (`Prod-VPC`, 10.0.0.0/16) designed for resilience, spanning across two Availability Zones (AZs).
- **Subnet Architecture**:
  - **Public Subnets**: Host internet-facing resources like the Application Load Balancer and NAT Gateway.
  - **Private Subnets**: House the protected application servers and database, ensuring they have no direct connection to the public internet.
- **Amazon RDS (PostgreSQL)**: A managed `prod-db` PostgreSQL instance is deployed in the private subnets. This managed service handles automated backups, patching, scaling, and multi-AZ failover.

### 2. Security & Configuration (Zero-Trust Model)
- **Security Groups (Firewalls)**: A strict firewall rule "chain" is enforced:
  - `lb-sg`: Allows public HTTPS (Port 443) traffic.
  - `app-sg`: Allows traffic only from the load balancer on the application port (5000) and from within the VPC (for Lambda callbacks).
  - `db-sg`: Allows only PostgreSQL (Port 5432) traffic from the application servers (`app-sg`).
- **AWS Systems Manager (SSM) Parameter Store**: All secrets (database credentials, Flask `SECRET_KEY`, API keys) are securely stored as encrypted `SecureString` parameters, providing security at rest, IAM-based access control, and centralized management.
- **IAM Roles**: Enforcing the principle of "least privilege", EC2 instances are assigned an `AppServerRole` authorizing read-only access to specific SSM parameters (`/prod/app/`).

### 3. Application Infrastructure
- **Application Load Balancer (ALB)**: The `prod-alb` routes traffic through public subnets. It performs **SSL Termination** (decrypting HTTPS traffic), continuous **Health Checks** (`/health`), and **Routing** to distribute traffic among healthy ASG instances.
- **Serverless Code Execution (AWS Lambda & API Gateway)**:
  - Untrusted user code is isolated from the main app. The Flask server forwards execution requests to an Amazon API Gateway (`ExecutionAPI`).
  - The API Gateway invokes the `CodeExecutor` AWS Lambda function.
  - The Lambda function runs the code in a temporary, sandboxed environment and returns the output. This guarantees that malicious code cannot access the Flask server's environment variables, file system, or database.

### 4. Compute & Auto Scaling (Immutable Infrastructure)
- **Launch Template**: An `AppServer - Template` acts as the blueprint for new EC2 instances. It utilizes a User Data script to automatically bootstrap the server (installing dependencies, pulling code, securely fetching SSM parameters, and starting the Gunicorn server).
- **Auto Scaling Group (ASG)**: The `app-asg` uses the Launch Template to maintain a desired capacity across private subnets. Connected to the ALB's target group, it guarantees availability by substituting failed instances and enables scalability policies.