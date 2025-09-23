// Core zombie reaping pattern from Android
while (true) {
    auto pending_functions = epoll.Wait(epoll_timeout);
    if (!pending_functions->empty()) {
        ReapAnyOutstandingChildren();  // Always reap first
        for (const auto& function : *pending_functions) {
            (*function)();
        }
    }
}