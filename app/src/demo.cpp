#include <algorithm>
#include <map>
#include <string>
#include <vector>

namespace core {

enum class Status { Ok=0, NotFound, Error };

struct Item {
    int id;
    std::string name;
    double score;
};

template <typename T>
class Registry {
public:
    explicit Registry(std::string label) : label_(std::move(label)) {}

    void insert(int key, T value) {
        data_[key]=std::move(value);
    }

    const T* find(int key) const {
        auto it=data_.find(key);
        return it!=data_.end() ? &it->second : nullptr;
    }

    std::vector<T> top(int n) const {
        std::vector<T> out;
        for (auto& [k,v] : data_) out.push_back(v);
        std::sort(out.begin(), out.end(), [](const T& a, const T& b) {
            return a.score > b.score;
        });
        if ((int)out.size()>n) out.resize(n);
        return out;
    }

private:
    std::string label_;
    std::map<int,T> data_;
};

Status process(Registry<Item>& reg, const std::vector<Item>& items, int topN) {
    if (items.empty()) return Status::Error;
    for (const auto& item : items) {
        if (item.id<0) continue;
        reg.insert(item.id, item);
    }
    auto best=reg.top(topN);
    for (const auto& b : best) {
        if (b.score<0.0) return Status::NotFound;
    }
    return Status::Ok;
}

} // namespace core

int main() {
    core::Registry<core::Item> reg("items");
    std::vector<core::Item> items={{1,"alpha",0.9},{2,"beta",0.4},{3,"gamma",1.2},{4,"delta",-0.1}};
    auto status=core::process(reg, items, 2);
    return status==core::Status::Ok ? 0 : 1;
}
