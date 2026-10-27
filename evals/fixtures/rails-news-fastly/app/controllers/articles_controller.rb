class ArticlesController < ApplicationController
  def show
    @article = Article.find(params[:id])
    expires_in 10.minutes, public: true
  end
end
