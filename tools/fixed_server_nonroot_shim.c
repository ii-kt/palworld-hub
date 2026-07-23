/*
 * Reproduction-only shim for sandboxed CI containers that expose only UID 0.
 * PalServer refuses to start as root; this changes only its identity probe so
 * the exact, hash-verified server executable can initialize in that sandbox.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <netdb.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/types.h>

uid_t getuid(void) { return 1000; }
uid_t geteuid(void) { return 1000; }
gid_t getgid(void) { return 1000; }
gid_t getegid(void) { return 1000; }

/* Keep the reproduction process offline. Unix-domain IPC remains available. */
int connect(int fd, const struct sockaddr *address, socklen_t length) {
    static int (*real_connect)(int, const struct sockaddr *, socklen_t);
    if (address != NULL && (address->sa_family == AF_INET || address->sa_family == AF_INET6)) {
        errno = ENETUNREACH;
        return -1;
    }
    if (real_connect == NULL) {
        real_connect = dlsym(RTLD_NEXT, "connect");
    }
    return real_connect(fd, address, length);
}

ssize_t sendto(int fd, const void *buffer, size_t size, int flags,
               const struct sockaddr *address, socklen_t length) {
    static ssize_t (*real_sendto)(int, const void *, size_t, int,
                                  const struct sockaddr *, socklen_t);
    if (address != NULL && (address->sa_family == AF_INET || address->sa_family == AF_INET6)) {
        errno = ENETUNREACH;
        return -1;
    }
    if (real_sendto == NULL) {
        real_sendto = dlsym(RTLD_NEXT, "sendto");
    }
    return real_sendto(fd, buffer, size, flags, address, length);
}

ssize_t sendmsg(int fd, const struct msghdr *message, int flags) {
    static ssize_t (*real_sendmsg)(int, const struct msghdr *, int);
    const struct sockaddr *address = message == NULL ? NULL : message->msg_name;
    if (address != NULL && (address->sa_family == AF_INET || address->sa_family == AF_INET6)) {
        errno = ENETUNREACH;
        return -1;
    }
    if (real_sendmsg == NULL) {
        real_sendmsg = dlsym(RTLD_NEXT, "sendmsg");
    }
    return real_sendmsg(fd, message, flags);
}
