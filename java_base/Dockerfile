#docker build -t java_base:latest .

FROM base:latest

#######################################################
# # 安装必要的依赖 https://jdk.java.net
# RUN wget https://download.java.net/java/GA/jdk23.0.2/6da2a6609d6e406f85c491fcb119101b/7/GPL/openjdk-23.0.2_linux-aarch64_bin.tar.gz && \
#     tar -xzf openjdk-23.0.2_linux-aarch64_bin.tar.gz -C /opt && \
#     mv /opt/jdk-23.0.2 /opt/java && \
#     rm -rf openjdk-23.0.2_linux-aarch64_bin.tar.gz
#  
# # 设置环境变量
# ENV JAVA_HOME /opt/java
# ENV PATH $PATH:$JAVA_HOME/bin
#######################################################

COPY zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64.tar.gz .
RUN tar -xzf zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64.tar.gz -C /opt && \
    mv /opt/zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64 /opt/java && \
    rm -rf zulu8.84.0.15-ca-jdk8.0.442-linux_aarch64.tar.gz
ENV JAVA_HOME /opt/java
ENV PATH $PATH:$JAVA_HOME/bin