#include <iostream>
#include <string>
#include <vector>

struct Match {
    std::string student;
    int score;
};

bool comes_before(const Match& left, const Match& right) {
    if (left.score != right.score) {
        return left.score > right.score;
    }
    return left.student <= right.student;
}

void merge(std::vector<Match>& matches, std::vector<Match>& buffer,
           int first, int middle, int last) {
    int left = first;
    int right = middle;
    int output = first;

    while (left < middle && right < last) {
        if (comes_before(matches[left], matches[right])) {
            buffer[output++] = matches[left++];
        } else {
            buffer[output++] = matches[right++];
        }
    }
    while (left < middle) {
        buffer[output++] = matches[left++];
    }
    while (right < last) {
        buffer[output++] = matches[right++];
    }
    for (int index = first; index < last; ++index) {
        matches[index] = buffer[index];
    }
}

void merge_sort(std::vector<Match>& matches, std::vector<Match>& buffer,
                int first, int last) {
    if (last - first < 2) {
        return;
    }
    const int middle = first + (last - first) / 2;
    merge_sort(matches, buffer, first, middle);
    merge_sort(matches, buffer, middle, last);
    merge(matches, buffer, first, middle, last);
}

int main() {
    std::vector<Match> matches = {
        {"Maya", 100}, {"Aarav", 50}, {"Ishaan", 50}, {"Zoya", 0}
    };
    std::vector<Match> buffer(matches.size());
    merge_sort(matches, buffer, 0, static_cast<int>(matches.size()));

    std::cout << "Campus Skill Exchange matches (highest score first)\n";
    for (const Match& match : matches) {
        std::cout << match.student << ": " << match.score << "/100\n";
    }
    return 0;
}
