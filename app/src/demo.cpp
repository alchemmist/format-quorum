#include <algorithm>
#include <concepts>
#include <format>
#include <map>
#include <print>
#include <ranges>
#include <source_location>
#include <span>
#include <string>
#include <string_view>
#include <vector>

// ── Concepts ──────────────────────────────────────────────────────────────────

template<typename T>
concept Scorable = requires(T t) {
    { t.score } -> std::convertible_to<double>;
    { t.id } -> std::convertible_to<int>;
};

template<typename T>
concept Printable = requires(T t) {
    { t.name } -> std::convertible_to<std::string_view>;
};

// ── Macros ────────────────────────────────────────────────────────────────────

#define ASSERT_VALID(x, msg) \
    do { \
        if (!(x)) throw std::runtime_error(msg); \
    } while (0)

#define DEFINE_STATUS_ENUM(Name, ...) \
    enum class Name { __VA_ARGS__ }

// ── Enums & structs ───────────────────────────────────────────────────────────

DEFINE_STATUS_ENUM(Status, Ok=0, NotFound, Error);

struct Item {
    int id;
    std::string name;
    double score;
};

// ── Templates ─────────────────────────────────────────────────────────────────

template<Scorable T>
struct ScoredView {
    std::span<const T> items;

    auto top(int n) const {
        return items
            | std::views::filter([](const T& t){ return t.id>=0; })
            | std::views::transform([](const T& t) -> std::pair<double,const T*> { return {t.score,&t}; })
            | std::ranges::to<std::vector>();
    }
};

template<typename T>
requires Scorable<T> && Printable<T>
class Registry {
public:
    explicit Registry(std::string label) : label_(std::move(label)) {}

    void insert(int key, T value) {
        ASSERT_VALID(key>=0, "negative key");
        data_[key]=std::move(value);
    }

    const T* find(int key) const {
        auto it=data_.find(key);
        return it!=data_.end() ? &it->second : nullptr;
    }

    std::vector<T> top(int n) const {
        auto all=data_
            | std::views::values
            | std::ranges::to<std::vector>();
        std::ranges::sort(all,[](const T& a,const T& b){ return a.score>b.score; });
        if (std::cmp_greater(n,all.size())) return all;
        return {all.begin(),all.begin()+n};
    }

    void print_all(const std::source_location loc=std::source_location::current()) const {
        std::println("[{}:{}] registry '{}' ({} items):",loc.file_name(),loc.line(),label_,data_.size());
        for (auto& [k,v] : data_) {
            std::println("  [{:>3}] {:<20} score={:.3f}",k,v.name,v.score);
        }
    }

private:
    std::string label_;
    std::map<int,T> data_;
};

// ── Lambdas & ranges ──────────────────────────────────────────────────────────

auto make_filter(double min_score) {
    return [min_score]<Scorable T>(const T& item) noexcept {
        return item.score>=min_score;
    };
}

template<std::ranges::input_range R>
requires Scorable<std::ranges::range_value_t<R>>
auto summarize(R&& range) -> std::string {
    auto scores=std::forward<R>(range)
        | std::views::transform([](const auto& t){ return t.score; })
        | std::ranges::to<std::vector>();
    double sum=std::ranges::fold_left(scores,0.0,std::plus{});
    return std::format("count={} sum={:.2f} avg={:.2f}",scores.size(),sum,scores.empty()?0.0:sum/scores.size());
}

// ── main ──────────────────────────────────────────────────────────────────────

int main() {
    Registry<Item> reg("items");
    std::vector<Item> items={{1,"alpha",0.9},{2,"beta",0.4},{3,"gamma",1.2},{4,"delta",-0.1},{5,"epsilon",0.75}};

    for (auto& item : items) {
        if (item.id>=0) reg.insert(item.id,item);
    }

    reg.print_all();

    auto best=reg.top(3);
    auto good=items|std::views::filter(make_filter(0.5))|std::ranges::to<std::vector>();

    std::println("top-3:");
    for (const auto& b : best) {
        std::println("  {} -> {:.3f}",b.name,b.score);
    }

    std::println("summary (all): {}",summarize(items));
    std::println("summary (good): {}",summarize(good));

    return best.empty()||best.front().score<=0.0 ? 1 : 0;
}
